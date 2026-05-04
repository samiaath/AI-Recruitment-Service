import json
from typing import Dict, Any, List
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..config import settings
from ..models import ExperienceType, ScoreBreakdown

# Initialisation Globale pour optimiser les appels répétitifs (singleton)
MISTRAL_CLIENT_INSTANCE = None
def get_mistral_client():
    global MISTRAL_CLIENT_INSTANCE
    if MISTRAL_CLIENT_INSTANCE is None:
        MISTRAL_CLIENT_INSTANCE = MistralAsyncClient(api_key=settings.mistral_api_key)
    return MISTRAL_CLIENT_INSTANCE

_SCORING_PROMPT = """
Tu es un évaluateur RH expert. Note ce candidat par rapport à l'offre d'emploi.
Retourne UNIQUEMENT un JSON strict, sans texte avant ou après.

OFFRE D'EMPLOI :
{job_description}

PROFIL CANDIDAT :
Compétences extraites : {skills}
XP totale (pro + stages + bénévolat) : {total_years} ans
XP professionnelle seule (hors stages) : {pro_years} ans
Expériences réelles (projets académiques exclus) :
{experiences}
Formation :
{education}

RÈGLES DE NOTATION MATHEMATHIQUES — APPLIQUE-LES STRICTEMENT :
1. skills_match (0-100) : (nb compétences de l'offre explicitement présentes dans le profil) ÷ (nb compétences demandées *par l'offre*) × 100.
2. experience_years (0-100) : Calcule la durée D'EXPÉRIENCE PERTINENTE (en années) qui correspond *strictement* au domaine du poste. Note cette durée pertinente par rapport aux exigences de l'offre. Ne prends PAS en compte les années d'expérience hors-sujet. Si l'offre exige 2 ans en .NET et le candidat a 2 mois, score < 20.
3. education_level (0-100) : Adéquation du diplôme *par rapport à celui exigé dans l'offre*.
4. seniority_match (0-100) : Les responsabilités du candidat correspondent-elles à celles *attendues dans l'offre* ?

Tu dois aussi générer "strengths" (points forts pertinents pour l'offre), "weaknesses" (écarts selon l'offre) et "summary" (conclusion).

FORMAT JSON :
{{
  "skills_match":     50.0,
  "experience_years": 50.0,
  "education_level":  50.0,
  "seniority_match":  50.0,
  "missing_skills":   ["comp1", "comp2"],
  "confidence":       0.9,
  "strengths":        "Points forts très courts",
  "weaknesses":       "Écarts majeurs très courts",
  "summary":          "Conclusion très courte",
  "explanation":      "Justification 1 phrase maximale"
}}
"""

async def compute_score(ai_extracted: Any, description_poste: str) -> Dict[str, Any]:
    weights = settings.scoring_weights
    if not description_poste or description_poste.strip() == "":
        bd = ScoreBreakdown(skills_match=50, experience_years=50, education_level=50, seniority_match=50)
        return _build_result(weights.weighted_score(50, 50, 50, 50), bd, 0.5, "Aucune description de poste fournie, score neutre.", "TBD", "TBD")

    skills_text = ", ".join([getattr(s, "SkillDescription", str(s)) for s in getattr(ai_extracted, "skills", [])]) or "Aucune"
    
    exp_lines = []
    pro_years = 0.0
    
    for e in getattr(ai_extracted, "experiences", []):
        exp_type = getattr(e, "experience_type", None)
        if exp_type == ExperienceType.ACADEMIC: continue
        badge = {"professional": "PRO", "internship": "STAGE", "volunteering": "BÉNÉVOLAT", "freelance": "FREELANCE"}.get(getattr(exp_type, "value", str(exp_type)), "?")
        desc = getattr(e, "ExperienceDescription", "") or ""
        line = f"  [{badge}] {getattr(e, 'ExperiencePosition', '?')} @ {getattr(e, 'ExperienceCompany', '?')}"
        exp_lines.append(line + f": {desc}")
        
    exp_text = "\n".join(exp_lines) or "Aucune expérience réelle renseignée"
    edu_text = "\n".join([f"- {getattr(d, 'Description', '?')} ({getattr(d, 'DegreeObtentionYear', '?')})" for d in getattr(ai_extracted, "degrees", [])]) or "Aucune formation"
    
    total_years = getattr(ai_extracted, "total_years_experience", 0.0) or 0.0
    pro_years = getattr(ai_extracted, "professional_years_only", total_years) or total_years

    prompt = _SCORING_PROMPT.format(job_description=description_poste, skills=skills_text, total_years=total_years, pro_years=pro_years, experiences=exp_text, education=edu_text)

    try:
        client = get_mistral_client()
        response = await client.chat(
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        eval_json = json.loads(response.choices[0].message.content)
        s_skills = float(eval_json.get("skills_match", 50))
        s_exp = float(eval_json.get("experience_years", 50))
        s_edu = float(eval_json.get("education_level", 50))
        s_sen = float(eval_json.get("seniority_match", 50))
        conf = float(eval_json.get("confidence", 1.0))
        strengths = eval_json.get("strengths", "Aucune correspondance")
        weaknesses = eval_json.get("weaknesses", "Aucun manque majeur")
        summary = eval_json.get("summary", "")
        missing_skills = eval_json.get("missing_skills", [])
        explanation = eval_json.get("explanation", "")
        
        bd = ScoreBreakdown(skills_match=round(s_skills, 1), experience_years=round(s_exp, 1), education_level=round(s_edu, 1), seniority_match=round(s_sen, 1))
        final_score = weights.weighted_score(s_skills, s_exp, s_edu, s_sen)
        return _build_result(final_score, bd, conf, summary, strengths, weaknesses, missing_skills, explanation)
        
    except Exception as e:
        bd = ScoreBreakdown(skills_match=50, experience_years=50, education_level=50, seniority_match=50)
        return _build_result(50.0, bd, 0.0, "Erreur d'analyse sémantique. Score neutre par défaut.", "Erreur", "Erreur", [], "Erreur d'analyse sémantique.")

def _score_level(score: float) -> str:
    if score >= 80: return "Excellent"
    if score >= 65: return "Bon"
    if score >= 45: return "Moyen"
    return "Faible"

def _build_result(score, breakdown, confidence, summary, strengths, weaknesses, missing_skills=None, explanation="") -> Dict:
    w = settings.scoring_weights
    pts_faibles = weaknesses
    if missing_skills and len(missing_skills) > 0:
        pts_faibles += f" (Manques: {', '.join(missing_skills[:3])})"
        
    short_explanation = f"Points forts : {strengths} | Points faibles : {pts_faibles} | Conclusion : {summary}"
    
    return {
        "score": score,
        "level": _score_level(score),
        "breakdown": breakdown.dict(),
        "missing_skills": missing_skills or [],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "summary": short_explanation,
        "ApplicationEvaluationExplanation": short_explanation
    }
