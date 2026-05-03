import json
from typing import Dict, Any, List
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..config import settings

# Initialisation Globale pour optimiser les appels répétitifs (singleton)
MISTRAL_CLIENT_INSTANCE = None
def get_mistral_client():
    global MISTRAL_CLIENT_INSTANCE
    if MISTRAL_CLIENT_INSTANCE is None:
        MISTRAL_CLIENT_INSTANCE = MistralAsyncClient(api_key=settings.mistral_api_key)
    return MISTRAL_CLIENT_INSTANCE

async def compute_score(ai_extracted: Any, description_poste: str) -> Dict[str, Any]:
    """
    Scoring sémantique complet effectué par LLM, en croisant le CV complet extrait
    et la description du poste. Finit l'époque de la regex floue.
    Cela retourne un JSON structuré.
    """
    if not description_poste or description_poste.strip() == "":
        return {
            "score": 50.0,
            "summary": "Aucune description de poste fournie, score neutre.",
            "strengths": "TBD",
            "weaknesses": "TBD"
        }

    # Préparer le texte de contexte depuis le CV structuré
    skills_text = ", ".join([s.SkillDescription for s in ai_extracted.skills])
    exp_text = "\\n".join([f"- {e.ExperiencePosition} a {e.ExperienceCompany} ({e.ExperienceStartDate} a {e.ExperienceEndDate}): {e.ExperienceDescription}" for e in ai_extracted.experiences])
    edu_text = "\\n".join([f"- {d.Description} en {d.DegreeObtentionYear}" for d in ai_extracted.degrees])
    total_years = ai_extracted.total_years_experience

    prompt = f"""
Évaluez ce candidat de manière stricte, objective et sémantique par rapport à la description du poste.

Offre (Ce qui est demandé):
\"{description_poste}\"

Profil du candidat:
- Technologies extraites: {skills_text}
- Total: {total_years} années d'expérience (incluant stages)
- Expérience détaillée: 
{exp_text}
- Formation:
{edu_text}

RÈGLES CRITIQUES:
1. `strengths` (Points forts) : Listez en mots clés (3 puces maximum) UNIQUEMENT LES TECHNOLOGIES OU EXPERIENCES DE L'OFFRE (ce qui est demandé) que le profil possède bien. Vous avez l'interdiction formelle (CRITICAL) d'ajouter une compétence présente chez le candidat mais non demandée dans l'offre (ex: n'ajoutez jamais 'Angular' si l'offre demande 'C#').
2. `weaknesses` (Points faibles) : Listez en mots clés (3 puces maximum) UNIQUEMENT les exigences de l'offre MANQUANTES.
3. `summary` : Une seule phrase TRÈS COURTE (10 à 15 mots maximum) comme conclusion finale.

Retournez un JSON strict comme suit :
{{
    "score": <score float sur 100 basé sur un matching réel (compétences ET ancienneté)>,
    "strengths": "<puces très courtes des correspondances exactes avec l'offre (max 3)>",
    "weaknesses": "<puces très courtes des réels manques par rapport à l'offre (max 3)>",
    "summary": "<1 phrase courte de 15 mots max>"
}}
"""

    try:
        client = get_mistral_client()
        response = await client.chat(
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.1  # LLMOps (0.1 = plus déterministe et plus rapide)
        )
        
        eval_json = json.loads(response.choices[0].message.content)
        
        score = float(eval_json.get("score", 50.0))
        strengths = eval_json.get("strengths", "Aucune correspondance")
        weaknesses = eval_json.get("weaknesses", "Aucun manque majeur")
        summary = eval_json.get("summary", "")
        
        full_summary = f"Points forts : {strengths} | Points faibles : {weaknesses} | Explication : {summary}"

        return {
            "score": score,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "summary": full_summary
        }
        
    except Exception as e:
        print(f"Erreur lors du scoring AI Mistral: {e}")
        return {
            "score": 50.0,
            "summary": "Erreur d'analyse sémantique. Score neutre par défaut.",
            "strengths": "Erreur (Non determiné)",
            "weaknesses": "Erreur (Non determiné)"
        }

