"""
analyzer.py — Extraction structurée d'un CV via le LLM Mistral.

Rôle : à partir du texte brut d'un CV, produire un objet `ExtractedApplicationData`
(candidat, compétences, expériences, diplômes) prêt à être inséré en base.

Le LLM fait l'extraction sémantique (comprendre le texte) ; le code Python qui suit
fiabilise le résultat : nettoyage des valeurs, calcul déterministe des années
d'expérience, fallback regex pour le téléphone, garde-fous contre le bruit.
"""

import json
import re
import asyncio
from typing import List, Dict
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..models import (
    ExtractedApplicationData, Candidate, Skill, SkillGroup,
    Experience, ExperienceType, ApplicationDegree
)
from ..ingestion.read_db import (
    fetch_session_by_reference, fetch_all_institutions, fetch_all_study_levels
)
from ..config import settings

# Détecte une référence d'offre dans le texte (ex: "Réf: DEV-PY-01", "poste #1234").
REF_RE = re.compile(
    r"\b(?:ref(?:erence)?|poste|offre|job)[:\s#\-]*([A-Za-z0-9_\-]{3,})\b",
    re.IGNORECASE
)

# Client Mistral réutilisé entre les appels (singleton) pour éviter de le recréer.
_MISTRAL_CLIENT = None
def get_mistral_client() -> MistralAsyncClient:
    global _MISTRAL_CLIENT
    if _MISTRAL_CLIENT is None:
        _MISTRAL_CLIENT = MistralAsyncClient(api_key=settings.mistral_api_key)
    return _MISTRAL_CLIENT


async def _mistral_chat_with_retry(client, max_retries: int = 3, **kwargs):
    """
    Appelle l'API Mistral en réessayant en cas d'erreur réseau passagère
    (coupure, 429, 5xx). Backoff progressif : 1s puis 2s entre les tentatives.
    On NE met PAS de timeout : une réponse lente est attendue, pas une erreur.
    Si tous les essais échouent, on relève la dernière exception — l'appelant
    applique alors son fallback (résultat vide).
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await client.chat(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"[ANALYZER] Appel Mistral échoué (essai {attempt + 1}/{max_retries}) : {e} — nouvel essai...")
                await asyncio.sleep(2 ** attempt)
    raise last_error

async def get_cached_metadata():
    """
    Renvoie (institutions, niveaux d'études) pour alimenter le prompt.

    La mise en cache (avec expiration TTL) est gérée dans read_db : ces fonctions
    renvoient instantanément les données déjà chargées tant que le TTL n'est pas
    dépassé, puis rechargent depuis la base. Les deux requêtes partent en parallèle.
    """
    return await asyncio.gather(
        fetch_all_institutions(),
        fetch_all_study_levels()
    )


# Filet de sécurité : si le LLM ne renvoie pas de téléphone, on le cherche nous-mêmes
# dans le texte brut avec cette regex (gère les formats FR/TN/MA/DZ/BE/CH/US).
_PHONE_RE = re.compile(
    r"""
    (?:                        # ── formats avec indicatif international ──
        (?:\+|00)              # commence par + ou 00
        (?:33|216|212|213|32|41|1)  # indicatifs FR/TN/MA/DZ/BE/CH/US
        [\s.\-]?
        (?:\d[\s.\-]?){8,10}  # 8 à 10 chiffres
    |
        (?:0[0-9])             # ── format national (mobile commençant par 0) ──
        (?:[\s.\-]?\d){8}     # 8 chiffres restants
    )
    """,
    re.VERBOSE,
)


def _extract_phone_fallback(raw_text: str) -> str | None:
    """
    Extrait le premier numéro de téléphone trouvé dans le texte brut du CV.
    Utilisé comme fallback si le LLM ne retourne pas de numéro.
    Normalise le résultat : supprime les espaces/points/tirets excessifs.
    """
    if not raw_text:
        return None
    match = _PHONE_RE.search(raw_text)
    if not match:
        return None
    phone = match.group(0).strip()
    # Normalise : remplace séparateurs multiples par un espace unique
    phone = re.sub(r"[\s.\-]+", " ", phone).strip()
    # Tronque à 20 caractères (limite du champ)
    return phone[:20] if len(phone) >= 8 else None


_PROMPT = """
Tu es un parser de CV expert. Extrais les informations en JSON strict.
Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.

════════════════════════════════════════════════════════════════════════════
RÈGLES OBLIGATOIRES
════════════════════════════════════════════════════════════════════════════

── RÈGLE 0 : TÉLÉPHONE — EXTRACTION OBLIGATOIRE ──
Extrais TOUJOURS "ApplicationCandidatePhone1" si un numéro est présent.
Formats acceptés (tous les pays) :
  France    : 06 12 34 56 78 | +33 6 12 34 56 78 | 06.12.34.56.78
  Tunisie   : +216 12 345 678 | 00216 12 345 678 | 12 345 678
  Maroc     : +212 6 12 34 56 78 | 06 12 34 56 78
  Algérie   : +213 6 12 34 56 78
  Autre     : tout numéro de 8+ chiffres consécutifs
Retourne le numéro TEL QUEL (max 20 caractères), ne reformate PAS.
Si DEUX numéros : Phone1 = mobile/principal, Phone2 = fixe/secondaire.
NE retourne null que si AUCUN numéro n'est présent dans le CV.

── RÈGLE 1 : EXPÉRIENCES PROFESSIONNELLES (STRICT) ──
Le tableau "experiences" contient UNIQUEMENT les expériences PRO RÉELLES (CDI, CDD, stage en entreprise certifié, freelance averé avec un client explicite).
- EXCLUSION ABSOLUE : Études en cours, projets académiques, projets d'au-delà des cours, projets de classe, apprentissage personnel.
  * "Étudiante Ingénieure" n'est PAS une expérience, cest une formation (Degree).
  * Les rôles comme "Secrétaire Générale d'un Club" ou "Membre d'association" NE SONT PAS des expériences.
  * Les descriptions générales de tâches (ex: "Développement d'une application complète de gestion") NE SONT PAS des expériences. 
  * "Freelance" seul non rattaché à une entreprise / des clients facturés doit être ignoré.
- INCLUSION : Extrais 100% des expériences RÉELLES en entreprise avec un rôle clair et des dates claires. "Stage PFE" au sein d'une entreprise formelle compte comme expérience (type: internship).
- RÈGLE ABSOLUE : Si "ExperienceCompany" est null, introuvable, ou s'il s'agit d'un projet académique/personnel (ex: "Projet de classe"), la ligne DOIT ÊTRE TOTALEMENT IGNORÉE et ne pas être incluse dans "experiences".
- "ExperiencePosition" DOIT ÊTRE LE NOM DU POSTE / LE TITRE DU RÔLE UNIQUEMENT, court et concis (ex: "Analyste Développeur .NET Junior", "Stagiaire", "Développeur Backend", "Data Scientist"). Ne JAMAIS y mettre la description des tâches (ex: INVALIDE: "Développement d'une application de gestion"). Limité à quelques mots.
- TYPE : 
  * "professional" → CDI/CDD.
  * "freelance"    → Freelance RÉEL (avec clients facturés).
  * "internship"   → Stage conventionné, Alternance en entreprise.
  * "unknown"      → Si non clair, évitez de l'ajouter en tant qu'expérience.

── RÈGLE 1bis : DÉCOUPAGE EXPÉRIENCES ──
- UN poste chez UN employeur = UNE ligne.
- Freelance multi-clients : 
  * Si >3 missions distinctes → créer UNE ligne 'Freelance' globale.
  * Si 1-2 clients majeurs → UNE ligne par client.
- GAPS/TROUS : Ne JAMAIS inventer d'expériences non mentionnées pour combler les trous.

── RÈGLE 1ter : CAS SPÉCIAUX FREELANCE ET PROJETS ──
- 'Freelance chez ClientX' → ExperienceCompany='ClientX', type='freelance'
- Les projets du type "Projet PFE" ou "Développeur Full-Stack (Freelance / Personnel)" sans véritable employeur nommé : NE PAS les extraire comme une "experience". Ne les ajoutez qu'aux "skills".
- Freelance + CDI en parallèle → DEUX lignes distinctes (même si dates se chevauchent)

── RÈGLE 2 : COMPÉTENCES (GROUPÉES) ──
GROUPE LES COMPÉTENCES par catégorie sous le champ `category_name` (ex: "Langages de programmation", "Frameworks", "Outils", "Base de données", "Soft Skills", etc.) et liste les compétences dans le champ `skills`.
PRIORITÉ : Compétences de l'offre. LIMITE : N'invente rien, regroupe toutes celles trouvées dans le CV.

── RÈGLE 3 : DATES & DURÉES ──
- "YYYY-MM" obligatoire pour début/fin. "present" si en cours.
- Calcule "total_years_experience" sans double-comptage des chevauchements.
- "professional_years_only" exclut stages/bénévolat.

── RÈGLE 4 : ADAPTATION & DÉTAIL ──
L'OFFRE D'EMPLOI : {job_description}
- Utilise l'offre pour prioriser les skills mais n'ignore rien du CV.
- S'il y a plusieurs rôles/missions chez un même employeur, crée des entrées SÉPARÉES.

── RÈGLE 5 : DIPLÔMES — LABEL CLAIR ET INSTITUTIONS ──
- EXTRAIS UN LABEL CLAIR : Identifie le vrai nom du diplôme. OBLIGATOIRE : Remplis toujours la propriété "DegreeLabel" (ne mets JAMAIS null). Exemple: "Diplôme d'ingénieur en informatique", "Licence en gestion", "Master 2 Data Science". Résume l'intitulé de la formation proprement (max 100 car).
- ATTENTION AUX INSTITUTIONS ET NIVEAUX : Fais correspondre L'ÉCOLE et le NIVEAU D'ÉTUDE DU CV OBLIGATOIREMENT avec les libellés exacts fournis dans "INSTITUTIONS" et "NIVEAUX ÉTUDES" plus bas. 
  * Sois intelligent(e) sur le matching : "ENICAR" ou "Ecole national de carthage" correspond au libellé exact "Ecole Nationale d'Ingénieurs de Carthage".
  * Pour le niveau, "Cycle d'ingénieur" ou "Ecole d'ingénieur" correspond au libellé exact "ingénieur" dans la base.
- Seulement si l'école est TOTALEMENT absente de la liste, mets le nom trouvé. Mais FAVORISE TOUJOURS le libellé EXACT de la liste dans `institution_name` et `study_level_name`.

── RÈGLE 6 : DATES D'OBTENTION ──
- Année de fin ou estimation (ex: 2021).

── RÈGLE 7 : TRONCATURE ──
ExperienceCompany 50 | ExperiencePosition 50 | SkillDescription 100
DegreeLabel (intitulé) 100 | CandidateName 50 | Address 50

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
  "skills": [
    {{
      "category_name": "Langages de programmation",
      "skills": ["Python", "C#", "C++"]
    }},
    {{
      "category_name": "Bases de données",
      "skills": ["SQL", "MongoDB"]
    }}
  ],
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
      "DegreeLabel": "Diplôme d'ingénieur en informatique",
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


def sanitize_for_llm(text: str, max_tokens: int = 4000) -> str:
    """
    Sécurise le texte du CV avant de l'envoyer au LLM :
    - neutralise les tentatives d'injection de prompt (un CV malveillant pourrait
      contenir "ignore all previous instructions...") ;
    - tronque le texte pour rester dans la fenêtre de contexte (~max_tokens).
    """
    if not text: return ""
    important_patterns = [
        r"ignore\s+all\s+previous",
        r"system\s*:\s*you\s+are",
        r"</instructions>",
        r"assistant\s*:\s*",
    ]
    for pattern in important_patterns:
        text = re.sub(pattern, "[FILTERED]", text, flags=re.IGNORECASE)
    
    return text[:max_tokens * 4]

async def analyze_candidate(
    clean_text: str,
    raw_text_for_ref: str,
    email_meta: dict = None
) -> ExtractedApplicationData:
    """
    Point d'entrée principal de l'extraction.

    Étapes :
    1. Déterminer l'offre visée (référence + description) : fournie par l'appelant,
       sinon devinée dans le texte du CV, sinon session par défaut.
    2. Injecter les référentiels (institutions, niveaux) dans le prompt.
    3. Appeler Mistral pour obtenir un JSON structuré.
    4. Transformer ce JSON en objet Pydantic fiable via `_build_model`.
    """
    if not email_meta:
        email_meta = {}

    position_ref  = email_meta.get("PositionReference")
    position_desc = email_meta.get("PositionDescription")

    # Si l'offre n'est pas connue d'avance, on tente de la retrouver dans le texte du CV.
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

    institutions, study_levels = await get_cached_metadata()
    inst_str = "\n".join([f"  ID: {i['InstitutionID']} → {i['Name']}" for i in institutions])
    sl_str   = "\n".join([f"  ID: {s['StudyLevelID']} → {s['Name']}" for s in study_levels])

    cv_text_safe = sanitize_for_llm(clean_text)

    prompt = _PROMPT.format(inst_str=inst_str, sl_str=sl_str, cv_text=cv_text_safe, job_description=position_desc)
    try:
        client   = get_mistral_client()
        response = await _mistral_chat_with_retry(
            client,
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw_json = json.loads(response.choices[0].message.content)
    except Exception as e:
        # Échec définitif (après réessais) : on continue avec un JSON vide,
        # _build_model produira alors un candidat minimal plutôt que de planter.
        import traceback
        print(f"[ANALYZER] Mistral error: {e}")
        traceback.print_exc()
        raw_json = {}

    return _build_model(raw_json, email_meta, position_ref, position_desc, raw_text=clean_text)


def _safe(val, max_len: int = None):
    """
    Nettoie une valeur renvoyée par le LLM :
    - convertit les "null"/"none"/"n/a" textuels en vrai None ;
    - tronque à max_len si fourni.
    Évite d'insérer en base des chaînes parasites comme "unknown".
    """
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("null", "none", "unknown", "inconnu", "n/a", ""):
            return None
        if max_len:
            val = val[:max_len]
        return val
    return val


def _parse_date(date_str: str | None):
    """
    Convertit une date de CV en objet date Python. Gère plusieurs formats :
    "YYYY-MM", "YYYY", "Mois YYYY" (FR/EN), ainsi que "present"/"en cours".
    Renvoie None si rien d'exploitable n'est trouvé.
    """
    if not date_str:
        return None

    s = str(date_str).strip().lower()
    if s in ("present", "maintenant", "aujourd'hui", "current", "en cours"):
        from datetime import datetime
        return datetime.now()

    # Table des mois en français et anglais (abréviations incluses).
    months = {
        "jan": 1, "janv": 1, "janvier": 1, "january": 1,
        "feb": 2, "fevr": 2, "fevrier": 2, "f\u00e9vrier": 2, "february": 2,
        "mar": 3, "mars": 3, "march": 3,
        "apr": 4, "avr": 4, "avril": 4, "april": 4,
        "may": 5, "mai": 5,
        "jun": 6, "juin": 6, "june": 6,
        "jul": 7, "juil": 7, "juillet": 7, "july": 7,
        "aug": 8, "août": 8, "aout": 8, "august": 8,
        "sep": 9, "sept": 9, "septembre": 9, "september": 10,
        "oct": 10, "octobre": 10, "october": 10,
        "nov": 11, "novembre": 11, "november": 11,
        "dec": 12, "decembre": 12, "d\u00e9cembre": 12, "december": 12
    }

    # Essai "Mois YYYY" (ex: "juin 2021")
    for m_name, m_num in months.items():
        if m_name in s:
            match_y = re.search(r"(\d{4})", s)
            if match_y:
                from datetime import date
                return date(int(match_y.group(1)), m_num, 1)

    # Essai "YYYY-MM" (ex: 2021-06)
    match_ym = re.search(r"(\d{4})[-/](\d{1,2})", s)
    if match_ym:
        from datetime import date
        return date(int(match_ym.group(1)), int(match_ym.group(2)), 1)

    # Essai "MM-YYYY" (ex: 06/2021)
    match_my = re.search(r"(\d{1,2})[-/](\d{4})", s)
    if match_my:
        from datetime import date
        return date(int(match_my.group(2)), int(match_my.group(1)), 1)

    # Essai "YYYY" seul → on suppose janvier
    match_y = re.search(r"(\d{4})", s)
    if match_y:
        from datetime import date
        return date(int(match_y.group(1)), 1, 1)

    return None


# Mots signifiant "encore en poste" (fin d'expérience non terminée).
_PRESENT_KEYWORDS = {"present", "présent", "maintenant", "aujourd'hui", "current", "en cours", "now", "actuel", "actuelle"}

def _calculate_total_years(experiences: List[Experience], filter_pro: bool = False) -> float:
    """
    Calcule le nombre total d'années d'expérience, SANS double-compter les
    périodes qui se chevauchent (ex: un freelance et un CDI en parallèle).

    Astuce : on remplit un ensemble (set) de couples (année, mois) travaillés.
    Comme un set ne garde pas les doublons, les chevauchements sont gérés
    automatiquement. Le total = nombre de mois uniques / 12.

    filter_pro=True : ne compte que le pro et le freelance (exclut stages/bénévolat).

    Selon le format de date :
    - "2020" → "2024" : soustraction d'années entières (colle à l'arrondi humain).
    - "2020" → "présent" : soustraction jusqu'à l'année courante.
    - "2020-06" → "2022-03" : décompte mois par mois (précision maximale).
    """
    if not experiences:
        return 0.0

    from datetime import datetime, date

    worked_months = set()
    today = datetime.now()

    for exp in experiences:
        # Mode "pro uniquement" : on saute les stages, le bénévolat, etc.
        if filter_pro and exp.experience_type not in (ExperienceType.PROFESSIONAL, ExperienceType.FREELANCE):
            continue

        start = _parse_date(exp.ExperienceStartDate)
        if not start:
            continue  # sans date de début, impossible de calculer une durée

        start_str = str(exp.ExperienceStartDate or "").strip()
        end_str   = str(exp.ExperienceEndDate   or "").strip().lower()

        end_is_present     = end_str in _PRESENT_KEYWORDS or end_str == ""
        start_is_year_only = len(start_str) == 4 and start_str.isdigit()
        end_is_year_only   = len(end_str)   == 4 and end_str.isdigit()

        end = _parse_date(exp.ExperienceEndDate) if not end_is_present else today

        if start_is_year_only and (end_is_year_only or end_is_present):
            # Dates en années seules → on ajoute tous les mois des années pleines.
            for y in range(start.year, end.year):
                for m in range(1, 13):
                    worked_months.add((y, m))
        else:
            curr  = date(start.year, start.month, 1)
            limit = date(end.year,   end.month,   1)
            if curr == limit:
                # Début = fin (date unique) → on crédite 6 mois minimum (stage court).
                for m in range(1, 7):
                    worked_months.add((curr.year, m))
            else:
                # On avance mois par mois du début jusqu'à la fin.
                while curr <= limit:
                    worked_months.add((curr.year, curr.month))
                    if curr.month == 12:
                        curr = date(curr.year + 1, 1, 1)
                    else:
                        curr = date(curr.year, curr.month + 1, 1)

    return round(len(worked_months) / 12.0, 1)


def _normalize_phone_digits(phone: str | None) -> str | None:
    """
    Normalise un numéro de téléphone en ne gardant que ses chiffres.

    Exemples :
      '+33 6 12 34 56 78'  → '33612345678'
      '06.12.34.56.78'     → '0612345678'
      '+216 55 44 33 22'   → '21655443322'
      '00216 55 44 33 22'  → '0021655443322'  (tronqué à 15)

    On conserve max 15 chiffres (format ITU-T E.164 sans le +).
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:          # trop court pour être un vrai numéro
        return None
    return digits[:15]           # max 15 chiffres (standard international)


def _build_model(data, email_meta, position_ref, position_desc, raw_text: str = "") -> ExtractedApplicationData:
    """
    Transforme le JSON brut du LLM en objet `ExtractedApplicationData` fiable.

    C'est ici qu'on applique tous les garde-fous : nettoyage des champs,
    fallback téléphone, filtrage des fausses expériences, valeurs par défaut
    pour les diplômes, et calcul déterministe des années d'expérience.
    """
    c = data.get("candidate", {})

    # ── Téléphone : on prend celui du LLM, sinon fallback regex, puis on ne garde
    #    que les chiffres (format homogène en base) ──
    phone1_raw = _safe(c.get("ApplicationCandidatePhone1"), 30)
    phone2_raw = _safe(c.get("ApplicationCandidatePhone2"), 30)
    if not phone1_raw:
        phone1_raw = _extract_phone_fallback(raw_text)
        if phone1_raw:
            print(f"[ANALYZER] 📞 Téléphone extrait via regex fallback : {phone1_raw}")
    phone1_llm = _normalize_phone_digits(phone1_raw)
    phone2_llm = _normalize_phone_digits(phone2_raw)

    candidate = Candidate(
        ApplicationEmail=_safe(c.get("ApplicationEmail"), 50) or email_meta.get("email", "unknown@email.com"),
        ApplicationCandidateName=_safe(c.get("ApplicationCandidateName"), 50) or email_meta.get("name", "Candidat Anonyme"),
        ApplicationCandidateBirthDate=_safe(c.get("ApplicationCandidateBirthDate"), 15),
        ApplicationCandidatePhone1=phone1_llm,
        ApplicationCandidatePhone2=phone2_llm,
        ApplicationCandidateAddress=_safe(c.get("ApplicationCandidateAddress"), 50),
    )

    # Compétences : regroupées par catégorie (ex: "Langages : Python, C#").
    parsed_skills = []
    for sk in data.get("skills", []):
        if isinstance(sk, dict):
            cat = _safe(sk.get("category_name", "Autres"), 50)
            s_list = [_safe(s, 50) for s in sk.get("skills", []) if isinstance(s, str)]
            if s_list:
                parsed_skills.append(SkillGroup(category_name=cat, skills=s_list))

    # Expériences : on convertit le type, on filtre le bruit académique.
    experiences = []
    for exp in data.get("experiences", []):
        raw_type = exp.get("experience_type", "unknown")
        try:
            exp_type = ExperienceType(raw_type)
        except ValueError:
            exp_type = ExperienceType.UNKNOWN

        comp = _safe(exp.get("ExperienceCompany"), 50)
        pos = _safe(exp.get("ExperiencePosition"), 50)
        start_date = _safe(exp.get("ExperienceStartDate"), 10)
        
        # FILTRE DE SÉCURITÉ : On ignore les "expériences" sans entreprise ET sans date 
        # (souvent du bruit académique ou des titres de section)
        if not comp and not start_date:
            continue
            
        # Filtre additionnel : ignorer si ça ressemble à une mention de formation
        pos_lower = (pos or "").lower()
        if not comp and ("étudiant" in pos_lower or "formation" in pos_lower or "cursus" in pos_lower):
            continue

        experiences.append(Experience(
            experience_type=exp_type,
            ExperienceStartDate=start_date,
            ExperienceEndDate=_safe(exp.get("ExperienceEndDate"), 10),
            ExperienceCompany=comp.rstrip(".,- ") if comp else None,
            ExperiencePosition=pos.rstrip(".,- ") if pos else None,
            ExperienceDescription=_safe(exp.get("ExperienceDescription")),
            duration_months=exp.get("duration_months") if isinstance(exp.get("duration_months"), (int, float)) else None,
        ))

    # Diplômes : on valide les IDs (institution/niveau) et on garantit un label.
    degrees = []
    for deg in data.get("degrees", []):
        # Les IDs doivent être des entiers valides, sinon on les ignore (résolus plus tard en base).
        inst_id = deg.get("institution_id")
        if inst_id is not None and not isinstance(inst_id, int):
            inst_id = None
        sl_id = deg.get("study_level_id")
        if sl_id is not None and not isinstance(sl_id, int):
            sl_id = None
        raw_year = deg.get("DegreeObtentionYear")
        safe_year = str(raw_year) if raw_year is not None else None

        # DegreeLabel est obligatoire en base : valeur de repli si le LLM ne l'a pas fourni.
        degree_label = str(deg.get("DegreeLabel") or deg.get("Description") or "Titre non précisé")
        
        degrees.append(ApplicationDegree(
            DegreeObtentionYear=safe_year,
            DegreeLabel=degree_label[:100],
            institution_id=inst_id,
            institution_name=_safe(deg.get("institution_name")),
            study_level_id=sl_id,
            study_level_name=_safe(deg.get("study_level_name")),
        ))

    # Les années d'XP sont recalculées par notre code (plus fiable que le LLM pour les maths).
    return ExtractedApplicationData(
        candidate=candidate,
        skills=parsed_skills,
        experiences=experiences,
        degrees=degrees,
        total_years_experience=_calculate_total_years(experiences, filter_pro=False),
        professional_years_only=_calculate_total_years(experiences, filter_pro=True),
        session_position_reference=position_ref,
        session_position_description=position_desc,
    )