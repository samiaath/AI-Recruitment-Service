import json
import asyncio
from typing import Dict, Any, List
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..config import settings
from ..models import ExperienceType, ScoreBreakdown

# Client Mistral réutilisé entre les appels (singleton).
MISTRAL_CLIENT_INSTANCE = None
def get_mistral_client():
    global MISTRAL_CLIENT_INSTANCE
    if MISTRAL_CLIENT_INSTANCE is None:
        MISTRAL_CLIENT_INSTANCE = MistralAsyncClient(api_key=settings.mistral_api_key)
    return MISTRAL_CLIENT_INSTANCE


async def _mistral_chat_with_retry(client, max_retries: int = 3, **kwargs):
    """
    Appelle l'API Mistral en réessayant en cas d'erreur réseau passagère.
    Backoff : 1s puis 2s. Pas de timeout (une réponse lente reste valide).
    Si tous les essais échouent, l'exception remonte et l'appelant applique
    son score neutre de secours.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await client.chat(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"[SCORER] Appel Mistral échoué (essai {attempt + 1}/{max_retries}) : {e} — nouvel essai...")
                await asyncio.sleep(2 ** attempt)
    raise last_error

_SCORING_PROMPT = """
Tu es un évaluateur RH expert et moderne. Ton but est d'aligner ta notation SUR LES EXIGENCES DE L'OFFRE D'EMPLOI de manière absolue.
Tu dois scorer le profil d'un candidat STRICTEMENT par rapport aux critères de l'offre d'emploi, en te basant sur les données extraites de son CV.
Retourne UNIQUEMENT un JSON strict.

RÈGLE D'OR : Les points forts (strengths) et les points faibles (weaknesses) doivent OBLIGATOIREMENT faire référence aux exigences mentionnées dans "OFFRE D'EMPLOI".

RÈGLE DE CALIBRAGE MÉTIER : Sois sobre et cohérent. N'accorde pas un score élevé à un profil qui ne couvre qu'une partie des exigences.
Un bon parcours ne compense pas l'absence des compétences clés du poste.
Le score doit refléter le niveau réel d'adéquation au poste, pas la qualité générale du CV.

ÉCHELLE DE NOTATION (RÉALISTE & VALORISANTE):

- 95-100 : EXCELLENT. Quasi toutes les exigences clés sont présentes, seniorité alignée.
- 85-94  : TRÈS BON. Le cœur du poste est couvert, avec un écart mineur.
- 70-84  : BON. Le profil est pertinent mais il manque au moins un bloc important.
- 50-69  : MOYEN. Correspondance partielle seulement.
- 0-49   : FAIBLE / INSUFFISANT. Le poste est mal couvert ou le domaine est trop éloigné.

RÈGLES D'ANCRAGE:
- Si le CV est COMPLETEMENT HORS DOMAINE (ex: Comptable pour un poste IT), tous les sous-scores (skills_match, experience_years, education_level, seniority_match) DOIVENT ÊTRE STRICTEMENT À 0.
- N'attribue jamais 90+ si une compétence clé du poste est absente.
- N'attribue jamais 80+ si l'expérience réelle est très en dessous de l'attendu.
- Si le CV est hors domaine total (ex: métier complètement différent du poste visé), le score doit être 0 pour toutes les catégories.
- Le score FINAL de 100 est RÉSERVÉ au cas où ABSOLUMENT toutes les exigences de l'offre sont couvertes, y compris les secondaires. Si au moins une exigence (même mineure comme une technologie secondaire ou un outil spécifique) est absente ou incertaine, le score MAXIMUM est 97.

PLANCHERS MINIMAUX OBLIGATOIRES — NE PAS DESCENDRE EN DESSOUS :
- Candidat avec Master/Doctorat + au moins 1 stage dans le domaine : experience_years ≥ 50
- Candidat avec Licence/Bachelor + au moins 1 stage dans le domaine : experience_years ≥ 45
- Candidat avec bootcamp récent + compétences actuelles demandées : skills_match ≥ 60
- Candidat avec 5+ ans d'expérience directe sur le poste : experience_years ≥ 85
- Bachelor/Licence + 5+ ans d'expérience : education_level ≥ 80 (l'expérience compense)
- Reconversion avec formation récente + compétences du poste présentes : skills_match ≥ 65

VALORISATION DE L'EXPÉRIENCE :
- Le BÉNÉVOLAT, le FREELANCE et les STAGES sont valorisés comme de l'expérience technique réelle
  pour les scores skills_match et experience_years. Ne pas les dévaloriser.
- Un candidat en reconversion avec un bootcamp récent et les compétences actuelles demandées
  peut atteindre 70-80 si les skills clés sont présents.
- Les projets académiques comptent comme expérience pratique des technologies.
- Les domaines UX/UI, BI/PowerBI, Embedded/C, SAP, Salesforce sont des SPÉCIALITÉS LÉGITIMES
  au même titre que le développement web : ne pas appliquer de malus de domaine.

LECTURE DES SIGNAUX DE L'OFFRE D'EMPLOI :
- Si l'offre mentionne "reconversion bienvenu(e)", "formation récente acceptée" ou "profil atypique
  bienvenu" : NE PAS pénaliser experience_years pour le manque d'historique dans le domaine.
  Les compétences du nouveau domaine + formation récente + 1 an d'XP dans la cible suffisent
  pour experience_years ≥ 65. L'offre a déjà intégré cette contrainte dans ses critères.
  De plus, si le candidat possède un Master ou Doctorat dans un domaine DIFFÉRENT mais valorisable
  (gestion, sciences, ingénierie) : education_level ≥ 75 car le niveau académique est transférable.
- Si l'offre mentionne "open source valorisé(e)", "contributions bénévoles valorisées" ou
  "projets personnels valorisés" : traite le bénévolat comme une expérience professionnelle
  complète pour experience_years. Ne pas appliquer de malus bénévolat.
- Si l'offre mentionne "débutant accepté", "junior bienvenu" ou "en cours de formation accepté" :
  le poste est calibré pour un profil en début de carrière. Pour un étudiant encore en formation
  (alternance, fin d'études), le statut étudiant doit être reflété : ne pas sur-valoriser
  experience_years ni seniority_match comme s'il s'agissait d'un professionnel confirmé.
  La capacité à assumer pleinement le rôle reste limitée par ce statut.
- Si le candidat est autodidacte (sans diplôme Bac+3 ou supérieur, uniquement baccalauréat /
  bootcamp / MOOC) : education_level doit refléter honnêtement l'absence de formation supérieure
  formelle, même si les skills techniques correspondent et que le poste ne requiert pas de diplôme.
  Ce critère reste un écart réel par rapport à un profil diplômé Bac+5.

SURQUALIFICATION :
- Si le candidat a 15+ ans d'expérience pour un poste sans mention "directeur/CTO/VP",
  baisser seniority_match à 55-65 maximum.
- Si le candidat a 10+ ans pour un poste sans mention "senior/lead/manager",
  baisser seniority_match à 70-80 maximum.
- La surqualification N'AFFECTE PAS skills_match, experience_years, education_level.

EXEMPLES DE CALIBRAGE CONCRETS :
- Master Data Science + 1 stage Data Engineer 6 mois → experience_years = 50, education_level = 95, skills_match selon compétences
- Licence Info + 1 stage Python 6 mois → experience_years = 45, education_level = 85, skills_match selon compétences
- Bootcamp Web + 1 an XP pro → experience_years = 60, education_level = 75, skills_match selon compétences
- 5 ans QA Selenium + Master → experience_years = 90, education_level = 100, skills_match selon compétences
- 6 ans BI PowerBI + Bachelor → experience_years = 90, education_level = 80, skills_match selon compétences
- 6 ans C Embarqué + Bachelor → experience_years = 90, education_level = 80, skills_match selon compétences
- 11 ans UX/UI Figma + Licence → experience_years = 95, education_level = 80, skills_match selon compétences
- Bootcamp 1 an + reconversion "bienvenue" dans l'offre + skills présentes → experience_years = 65, seniority_match = 75, score global 75-85
- Bénévolat open source 2 ans + stage + offre qui valorise l'open source → experience_years = 70 (traité comme XP pro), score global 80-88
- Alternance 1 an + étudiant ingénieur en cours + poste "débutant accepté" → experience_years = 55, seniority_match = 65 (plafond statut étudiant), score global 70-80
- Autodidacte Bac uniquement + XP solide + poste sans prérequis diplôme → education_level modéré (formation inférieure à Bac+3 = écart réel), experience_years selon XP réelle
- Reconversion + Master dans autre domaine + offre "reconversion bienvenue" → education_level ≥ 75 (Master valorisable), experience_years ≥ 65, score global 77-85
- Profil excellent mais une exigence (même secondaire) manquante → score FINAL max 97, jamais 100

CONSIGNES DE CALIBRAGE :
2. EXPÉRIENCES : Valorise le BÉNÉVOLAT et les PROJETS comme de l'XP pro. Ne pénalise PAS les pauses ou les reconversions réussies.
3. SENIORITÉ : Un candidat qui a le bon niveau (ex: Junior pour poste Junior) mérite 90+ en 'seniority_match'.

DÉTAIL DES SCORES :
1. skills_match (0-100) : Adéquation technologique.
2. experience_years (0-100) : Durée globale (tech + pro).
3. education_level (0-100) : Niveau de formation.
4. seniority_match (0-100) : Capacité à assumer le rôle.


OFFRE D'EMPLOI :
{job_description}

PROFIL CANDIDAT :
Compétences : {skills}
XP totale : {total_years} ans | XP pro : {pro_years} ans
Expériences :
{experiences}
Formation :
{education}

RÉDACTION (EN FRANÇAIS, TOUJOURS LIÉE AUX EXIGENCES DE L'OFFRE):

"strengths" → 2-3 points forts (les exigences de l'offre trouvées sur le cv) (7-8 mots)
"weaknesses" → 2-3 écarts (les exigences de l'offre NON trouvées) (7-8 mots)
"summary" → Conclusion (12 mots par rapport à l'offre)

ANALYSE CE CANDIDAT :
"""



async def compute_score(ai_extracted: Any, description_poste: str) -> Dict[str, Any]:
    weights = settings.scoring_weights
    if not description_poste or description_poste.strip() == "":
        bd = ScoreBreakdown(skills_match=50, experience_years=50, education_level=50, seniority_match=50)
        return _build_result(
            weights.weighted_score(50, 50, 50, 50), bd, 0.5,
            "Aucune description fournie, évaluation impossible",
            "Analyse impossible sans exigences",
            "Aucune exigence définie"
        )

    skills_text = ", ".join([getattr(s, "SkillDescription", str(s)) for s in getattr(ai_extracted, "skills", [])])[:200] or "Aucune"
    
    exp_lines = []
    for e in getattr(ai_extracted, "experiences", []):
        exp_type = getattr(e, "experience_type", None)
        if exp_type == ExperienceType.ACADEMIC: continue
        badge = {"professional": "PRO", "internship": "STAGE", "volunteering": "BÉNÉVOLAT", "freelance": "FREELANCE"}.get(getattr(exp_type, "value", str(exp_type)), "?")
        line = f"  [{badge}] {getattr(e, 'ExperiencePosition', '?')} @ {getattr(e, 'ExperienceCompany', '?')}"
        exp_lines.append(line)
        
    exp_text = "\n".join(exp_lines[:10]) or "Aucune"
    edu_text = "\n".join([f"- {getattr(d, 'DegreeLabel', '?')}" for d in getattr(ai_extracted, "degrees", [])])[:200] or "Aucune"
    
    total_years = getattr(ai_extracted, "total_years_experience", 0.0) or 0.0
    pro_years   = getattr(ai_extracted, "professional_years_only", 0.0) or 0.0

    prompt = _SCORING_PROMPT.format(
        job_description=description_poste[:500],
        skills=skills_text,
        total_years=total_years,
        pro_years=pro_years,
        experiences=exp_text,
        education=edu_text
    )

    try:
        client   = get_mistral_client()
        response = await _mistral_chat_with_retry(
            client,
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        eval_json = json.loads(response.choices[0].message.content)
        
        s_skills = float(eval_json.get("skills_match", 50))
        s_exp    = float(eval_json.get("experience_years", 50))
        s_edu    = float(eval_json.get("education_level", 50))
        s_sen    = float(eval_json.get("seniority_match", 50))
        conf     = float(eval_json.get("confidence", 1.0))
        
        strengths_raw  = eval_json.get("strengths", "")
        weaknesses_raw = eval_json.get("weaknesses", "")
        summary_raw    = eval_json.get("summary", "")
        
        if isinstance(strengths_raw, list):  strengths_raw  = " ".join(str(x) for x in strengths_raw)
        if isinstance(weaknesses_raw, list): weaknesses_raw = " ".join(str(x) for x in weaknesses_raw)
        if isinstance(summary_raw, list):    summary_raw    = " ".join(str(x) for x in summary_raw)
        
        strengths   = str(strengths_raw).strip()
        weaknesses  = str(weaknesses_raw).strip()
        summary_raw = str(summary_raw).strip()

        # FALLBACK INTELLIGENT
        if not strengths or len(strengths) < 10:
            strengths = _generate_fallback_strengths(ai_extracted, description_poste, s_skills, s_edu)
        
        if not weaknesses or len(weaknesses) < 10:
            weaknesses = _generate_fallback_weaknesses(ai_extracted, description_poste, s_exp, s_sen)
        
        if not summary_raw or len(summary_raw) < 10:
            summary_raw = _generate_fallback_summary(s_skills, s_exp, s_edu, s_sen)
        
        bd = ScoreBreakdown(
            skills_match=round(s_skills, 1),
            experience_years=round(s_exp, 1),
            education_level=round(s_edu, 1),
            seniority_match=round(s_sen, 1)
        )
        final_score = weights.weighted_score(s_skills, s_exp, s_edu, s_sen)
        
        return _build_result(final_score, bd, conf, summary_raw, strengths, weaknesses)
        
    except Exception as e:
        print(f"[SCORER] Erreur: {e}")
        bd = ScoreBreakdown(skills_match=50, experience_years=50, education_level=50, seniority_match=50)
        return _build_result(
            50.0, bd, 0.0,
            "Erreur système, score neutre appliqué",
            "Impossible d'évaluer par erreur technique",
            "Erreur d'analyse sémantique"
        )


def _generate_fallback_strengths(ai_extracted, description_poste: str, s_skills: float, s_edu: float) -> str:
    parts = []
    skills = [s.SkillDescription for s in getattr(ai_extracted, "skills", [])][:5]
    if skills and s_skills > 40: parts.append(f"Compétences : {', '.join(skills[:3])}")
    degrees = getattr(ai_extracted, "degrees", [])
    if degrees and s_edu > 60:
        desc = getattr(degrees[-1], "DegreeLabel", "diplôme")[:40]
        parts.append(f"formation {desc}")
    devops = [s for s in skills if s.lower() in ["docker", "kubernetes", "jenkins", "aws", "azure"]]
    if devops: parts.append(f"DevOps ({', '.join(devops[:2])})")
    return ", ".join(parts).capitalize() if parts else "Profil technique avec formation académique"


def _generate_fallback_weaknesses(ai_extracted, description_poste: str, s_exp: float, s_sen: float) -> str:
    parts = []
    total_years = getattr(ai_extracted, "total_years_experience", 0.0)
    pro_years   = getattr(ai_extracted, "professional_years_only", 0.0)
    if s_exp < 30: parts.append(f"Expérience très limitée ({total_years:.1f} an{'s' if total_years > 1 else ''}, dont {pro_years:.1f} pro)")
    elif s_exp < 50: parts.append(f"Expérience insuffisante (contexte académique dominant)")
    if s_sen < 40: parts.append("niveau junior vs confirmé/senior attendu")
    experiences = getattr(ai_extracted, "experiences", [])
    has_pro = any(getattr(e, "experience_type", None) == ExperienceType.PROFESSIONAL for e in experiences)
    if not has_pro: parts.append("absence expérience professionnelle")
    return ", ".join(parts).capitalize() if parts else "Niveau de séniorité inférieur aux attentes"


def _generate_fallback_summary(s_skills: float, s_exp: float, s_edu: float, s_sen: float) -> str:
    avg = (s_skills + s_exp + s_edu + s_sen) / 4
    if avg >= 80: return "Profil expérimenté parfaitement aligné avec les exigences"
    if avg >= 65: return "Profil qualifié globalement adapté avec ajustements mineurs"
    if avg >= 45: return "Profil intermédiaire partiellement adapté nécessitant accompagnement"
    if avg >= 30: return "Profil junior avec potentiel mais clairement sous-qualifié"
    return "Profil ne correspondant pas aux exigences minimales"


def _score_level(score: float) -> str:
    if score >= 80: return "Excellent"
    if score >= 65: return "Bon"
    if score >= 45: return "Moyen"
    return "Faible"


def _build_result(score, breakdown, confidence, summary_raw, strengths, weaknesses) -> Dict:
    explanation_parts = []
    
    if strengths and strengths.strip():
        explanation_parts.append(f"Points forts : {strengths.strip()}")
    
    if weaknesses and weaknesses.strip():
        explanation_parts.append(f"Points faibles : {weaknesses.strip()}")
    
    if summary_raw and summary_raw.strip():
        explanation_parts.append(f"Conclusion : {summary_raw.strip()}")
    
    short_explanation = " | ".join(explanation_parts) if explanation_parts else "Évaluation incomplète"
    
    return {
        "score": round(score, 2),
        "level": _score_level(score),
        "breakdown": breakdown.dict(),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "summary": short_explanation,
        #last stable version mais trop bavard 
        "ApplicationEvaluationExplanation": short_explanation
    }