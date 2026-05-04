import json
import re
import asyncio
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..models import (
    ExtractedApplicationData, Candidate, Skill,
    Experience, ExperienceType, ApplicationDegree
)
from ..ingestion.read_db import (
    fetch_session_by_reference, fetch_all_institutions, fetch_all_study_levels
)
from ..config import settings

REF_RE = re.compile(
    r"\b(?:ref(?:erence)?|poste|offre|job)[:\s#\-]*([A-Za-z0-9_\-]{3,})\b",
    re.IGNORECASE
)

_MISTRAL_CLIENT = None
def get_mistral_client() -> MistralAsyncClient:
    global _MISTRAL_CLIENT
    if _MISTRAL_CLIENT is None:
        _MISTRAL_CLIENT = MistralAsyncClient(api_key=settings.mistral_api_key)
    return _MISTRAL_CLIENT


_PROMPT = """
Tu es un parser de CV expert. Extrais les informations en JSON strict.
Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.

════════════════════════════════════════════════════════════════════════════
RÈGLES OBLIGATOIRES
════════════════════════════════════════════════════════════════════════════

── RÈGLE 1 : EXPÉRIENCES vs PROJETS ACADÉMIQUES ──
Le tableau "experiences" contient UNIQUEMENT des expériences hors cadre scolaire :
  ✅ INCLURE → CDI, CDD, stage en entreprise, stage en association, bénévolat, freelance
  ❌ EXCLURE → projet scolaire, PFE, mémoire, hackathon école, TP, TD

Pour classer, utilise "experience_type" :
  "professional" → CDI/CDD entreprise
  "internship" → Stage entreprise/asso/labo (hors école)
  "volunteering" → Bénévolat asso
  "freelance" → Mission indépendante
  "academic" → ⛔ Projet scolaire — NE PAS inclure
  "unknown" → Contexte insuffisant

DISTINGUER :
- Entité = ÉCOLE/UNIV/IUT → "academic" → EXCLURE
- "PFE","mémoire","soutenance","TP" → "academic" → EXCLURE
- "bénévolat" "volontaire" "membre" → "volunteering" → INCLURE
- "stage" + entreprise → "internship" → INCLURE

── RÈGLE 2 : COMPÉTENCES ──
Extrais depuis TOUTES sections (stages, projets académiques, formations)
Uniquement mots-clés ("Python","React"), jamais phrases

── RÈGLE 3 : DATES et DUREE ──
"YYYY-MM" pour expériences | "YYYY" pour diplômes
"present" si en cours | null si inconnu
Extrais avec precision "duration_months". Calcule minutieusement la duree des "volunteering" en te basant sur le fait qu'il s'agit d'un engagement associatif a temps partiel. Mais declare "duration_months" en mois calendaires. NE MULTIPLIE PAS par 20!

── RÈGLE 4 : ANNÉES D'EXPÉRIENCE PERTINENTES (SÉLÉCTIVES) ──
L'OFFRE D'EMPLOI EST : {job_description}
Tu ne dois compter QUE les expériences utiles et liées aux compétences de cette offre.
"total_years_experience" = Somme (en années, ex: 1.5) des expériences (pro + stage + freelance + bénévolat) QUI CORRESPONDENT AU POSTE.
"professional_years_only" = Somme (en années) des expériences pro et freelance QUI CORRESPONDENT AU POSTE.
Si une expérience (ex: bénévolat, stage) n'a rien à voir avec l'offre (ex: offre .NET, mais stage en marketing), sa durée = 0 dans le calcul. ATTENTION : si la personne est née en 2002, sois réaliste sur le cumul.


── RÈGLE 5 : DIPLÔMES ET FORMATIONS — EXHAUSTIVITÉ ET IDs/NOMS ──
- Tu DOIS extraire ABSOLUMENT TOUS les diplômes, cursus, baccalauréats, et cycles préparatoires (ex: Institut Préparatoire) présents dans le CV. Ne zappe aucune étape de la scolarité.
- Pour chaque formation, cherche dans les listes fournies ci-dessous :
  - Institution → si l'école/université s'y trouve, utilise son ID dans "institution_id" et laisse "institution_name" à null. Si elle n'y figure pas (ex: institut préparatoire spécifique ou lycée), mets "institution_id" à null et EXTRAIS LITTÉRALEMENT SON NOM dans "institution_name".
  - Niveau → si trouvé, utilise "study_level_id". Sinon, mets "study_level_id" à null et indique le niveau dans "study_level_name" (ex: "Cycle préparatoire", "Baccalauréat").
Il faut toujours renseigner l'ID ou le nom explicite pour l'institution et le niveau. Ne rate aucune école signalée dans le CV.

── RÈGLE 6 : DATES D'OBTENTION DES DIPLÔMES ──
Sois très intelligent pour déduire "DegreeObtentionYear" (l'année d'obtention).
- Si une fourchette est donnée ("2019 - 2021"), l'année d'obtention est "2021".
- Si c'est en cours ("2023 - présent"), essaie d'estimer l'année de fin normale (ex: Master en 2 ans = 2025) ou retourne simplement l'année actuelle si impossible.
- Cherche les dates autour du bloc de l'école dans le CV.

── RÈGLE 7 : TRONCATURE ──
ExperienceCompany 50 | ExperiencePosition 50 | SkillDescription 100
Description diplôme 100 | CandidateName 50 | Address 50

════════════════════════════════════════════════════════════════════════════
INSTITUTIONS (IDs EXACTS) :
{inst_str}

NIVEAUX ÉTUDES (IDs EXACTS) :
{sl_str}
════════════════════════════════════════════════════════════════════════════

JSON ATTENDU :
{{
  "candidate": {{
    "ApplicationEmail": "email ou null",
    "ApplicationCandidateName": "nom (max 50) ou null",
    "ApplicationCandidatePhone1": "phone ou null",
    "ApplicationCandidatePhone2": "phone2 ou null",
    "ApplicationCandidateAddress": "adresse (max 50) ou null",
    "ApplicationCandidateBirthDate": "YYYY-MM-DD ou null"
  }},
  "skills": ["Python","SQL"],
  "experiences": [
    {{
      "experience_type": "professional|internship|volunteering|freelance|unknown",
      "ExperienceStartDate": "YYYY-MM | null",
      "ExperienceEndDate": "YYYY-MM | present | null",
      "ExperienceCompany": "nom (max 50) | null",
      "ExperiencePosition": "titre (max 50) | null",
      "ExperienceDescription": "missions",
      "duration_months": 6.0
    }}
  ],
  "degrees": [
    {{
      "DegreeObtentionYear": "YYYY | null",
      "Description": "intitulé (max 100)",
      "institution_id": 2,
      "institution_name": "Nom école | null",
      "study_level_id": 3,
      "study_level_name": "Niveau diplôme | null"
    }}
  ],
  "total_years_experience": 2.5,
  "professional_years_only": 1.0
}}

CV :
{cv_text}
"""


async def analyze_candidate(
    clean_text: str,
    raw_text_for_ref: str,
    email_meta: dict = None
) -> ExtractedApplicationData:

    if not email_meta:
        email_meta = {}

    position_ref  = email_meta.get("PositionReference")
    position_desc = email_meta.get("PositionDescription")

    if not position_ref:
        match = REF_RE.search(raw_text_for_ref)
        if match:
            extracted_ref = match.group(1).upper()
            try:
                session_info  = await fetch_session_by_reference(extracted_ref)
                position_ref  = session_info["reference"]
                position_desc = session_info["description"]
            except Exception:
                position_ref  = extracted_ref
                position_desc = "Description non trouvée"
        else:
            position_ref  = "DEFAULT_SESSION"
            position_desc = "Session par défaut"

    institutions, study_levels = await asyncio.gather(
        fetch_all_institutions(),
        fetch_all_study_levels()
    )
    inst_str = "\n".join([f"  ID: {i['InstitutionID']} → {i['Name']}" for i in institutions])
    sl_str   = "\n".join([f"  ID: {s['StudyLevelID']} → {s['Name']}" for s in study_levels])

    prompt = _PROMPT.format(inst_str=inst_str, sl_str=sl_str, cv_text=clean_text, job_description=position_desc)
    try:
        client   = get_mistral_client()
        response = await client.chat(
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw_json = json.loads(response.choices[0].message.content)
    except Exception as e:
        import traceback
        print(f"[ANALYZER] Mistral error: {e}")
        traceback.print_exc()
        raw_json = {}

    return _build_model(raw_json, email_meta, position_ref, position_desc)


def _safe(val, max_len: int = None):
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("null", "none", "unknown", "inconnu", "n/a", ""):
            return None
        if max_len:
            val = val[:max_len]
        return val
    return val


def _build_model(data, email_meta, position_ref, position_desc) -> ExtractedApplicationData:
    c = data.get("candidate", {})
    candidate = Candidate(
        ApplicationEmail=_safe(c.get("ApplicationEmail"), 50) or email_meta.get("email", "unknown@email.com"),
        ApplicationCandidateName=_safe(c.get("ApplicationCandidateName"), 50) or email_meta.get("name", "Candidat Anonyme"),
        ApplicationCandidateBirthDate=_safe(c.get("ApplicationCandidateBirthDate"), 15),
        ApplicationCandidatePhone1=_safe(c.get("ApplicationCandidatePhone1"), 20),
        ApplicationCandidatePhone2=_safe(c.get("ApplicationCandidatePhone2"), 20),
        ApplicationCandidateAddress=_safe(c.get("ApplicationCandidateAddress"), 50),
    )

    skills = [Skill(SkillDescription=_safe(s, 100)) for s in data.get("skills", []) if isinstance(s, str) and s.strip()]

    experiences = []
    for exp in data.get("experiences", []):
        raw_type = exp.get("experience_type", "unknown")
        try:
            exp_type = ExperienceType(raw_type)
        except ValueError:
            exp_type = ExperienceType.UNKNOWN

        if exp_type == ExperienceType.ACADEMIC:
            print(f"[ANALYZER] Académique exclu : {exp.get('ExperiencePosition','?')} @ {exp.get('ExperienceCompany','?')}")
            continue

        experiences.append(Experience(
            experience_type=exp_type,
            ExperienceStartDate=_safe(exp.get("ExperienceStartDate"), 10),
            ExperienceEndDate=_safe(exp.get("ExperienceEndDate"), 10),
            ExperienceCompany=_safe(exp.get("ExperienceCompany"), 50),
            ExperiencePosition=_safe(exp.get("ExperiencePosition"), 50),
            ExperienceDescription=_safe(exp.get("ExperienceDescription")),
            duration_months=exp.get("duration_months") if isinstance(exp.get("duration_months"), (int, float)) else None,
        ))

    degrees = []
    for deg in data.get("degrees", []):
        inst_id = deg.get("institution_id")
        if inst_id is not None and not isinstance(inst_id, int):
            inst_id = None
        sl_id = deg.get("study_level_id")
        if sl_id is not None and not isinstance(sl_id, int):
            sl_id = None
        raw_year = deg.get("DegreeObtentionYear")
        safe_year = str(raw_year) if raw_year is not None else None
        degrees.append(ApplicationDegree(
            DegreeObtentionYear=safe_year,
            Description=_safe(deg.get("Description"), 100),
            institution_id=inst_id,
            institution_name=_safe(deg.get("institution_name")),
            study_level_id=sl_id,
            study_level_name=_safe(deg.get("study_level_name")),
        ))

    return ExtractedApplicationData(
        candidate=candidate,
        skills=skills,
        experiences=experiences,
        degrees=degrees,
        total_years_experience=float(data.get("total_years_experience") or 0.0),
        professional_years_only=float(data.get("professional_years_only") or 0.0),
        session_position_reference=position_ref,
        session_position_description=position_desc,
    )