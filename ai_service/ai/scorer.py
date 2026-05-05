import json
from typing import Dict, Any, List
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..config import settings
from ..models import ExperienceType, ScoreBreakdown

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
Compétences : {skills}
XP totale : {total_years} ans | XP pro : {pro_years} ans
Expériences :
{experiences}
Formation :
{education}

════════════════════════════════════════════════════════════════════════════
RÈGLES DE NOTATION
════════════════════════════════════════════════════════════════════════════
1. skills_match (0-100) : (compétences présentes) ÷ (compétences demandées) × 100
2. experience_years (0-100) : Expérience PERTINENTE vs exigences
3. education_level (0-100) : Diplôme vs offre
4. seniority_match (0-100) : Responsabilités vs attentes

════════════════════════════════════════════════════════════════════════════
RÉDACTION OBLIGATOIRE (EN FRANÇAIS)
════════════════════════════════════════════════════════════════════════════

"strengths" → 2-3 points forts PAR RAPPORT À L'OFFRE (10-15 mots)
"weaknesses" → 2-3 écarts PAR RAPPORT À L'OFFRE (10-15 mots)
"summary" → Conclusion générale (15-20 mots)

════════════════════════════════════════════════════════════════════════════
EXEMPLE CONCRET (Profil sous-qualifié)
════════════════════════════════════════════════════════════════════════════
{{
  "skills_match": 55.0,
  "experience_years": 20.0,
  "education_level": 75.0,
  "seniority_match": 25.0,
  "confidence": 0.85,
  "strengths": "Maîtrise C# et bases .NET exigés, diplôme d'ingénieur informatique",
  "weaknesses": "Expérience .NET très limitée (2 mois vs 2 ans requis), absence contexte production",
  "summary": "Profil junior avec potentiel technique mais clairement sous-qualifié pour les 2 ans .NET requis"
}}

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
    edu_text = "\n".join([f"- {getattr(d, 'Description', '?')}" for d in getattr(ai_extracted, "degrees", [])])[:200] or "Aucune"
    
    total_years = getattr(ai_extracted, "total_years_experience", 0.0) or 0.0
    pro_years = getattr(ai_extracted, "professional_years_only", 0.0) or 0.0

    prompt = _SCORING_PROMPT.format(
        job_description=description_poste[:500],
        skills=skills_text,
        total_years=total_years,
        pro_years=pro_years,
        experiences=exp_text,
        education=edu_text
    )

    try:
        client = get_mistral_client()
        response = await client.chat(
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        eval_json = json.loads(response.choices[0].message.content)
        
        s_skills = float(eval_json.get("skills_match", 50))
        s_exp = float(eval_json.get("experience_years", 50))
        s_edu = float(eval_json.get("education_level", 50))
        s_sen = float(eval_json.get("seniority_match", 50))
        conf = float(eval_json.get("confidence", 1.0))
        
        strengths = eval_json.get("strengths", "").strip()
        weaknesses = eval_json.get("weaknesses", "").strip()
        summary_raw = eval_json.get("summary", "").strip()
       
        
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
        desc = getattr(degrees[-1], "Description", "diplôme")[:40]
        parts.append(f"formation {desc}")
    devops = [s for s in skills if s.lower() in ["docker", "kubernetes", "jenkins", "aws", "azure"]]
    if devops: parts.append(f"DevOps ({', '.join(devops[:2])})")
    return ", ".join(parts).capitalize() if parts else "Profil technique avec formation académique"


def _generate_fallback_weaknesses(ai_extracted, description_poste: str, s_exp: float, s_sen: float) -> str:
    parts = []
    total_years = getattr(ai_extracted, "total_years_experience", 0.0)
    pro_years = getattr(ai_extracted, "professional_years_only", 0.0)
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