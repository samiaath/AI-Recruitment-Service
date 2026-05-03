import json
import re
from typing import Dict, Any
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage
from ..models import ExtractedApplicationData, Candidate, Skill, Experience, ApplicationDegree
from ..ingestion.read_db import fetch_session_by_reference, fetch_all_institutions, fetch_all_study_levels
from ..config import settings

REF_RE = re.compile(r"\b(?:ref|reference)[:\s-]*([A-Za-z0-9_-]+)\b", re.IGNORECASE)

# Initialisation Globale pour optimiser les appels répétitifs (singleton)
MISTRAL_CLIENT_INSTANCE = None
def get_mistral_client():
    global MISTRAL_CLIENT_INSTANCE
    if MISTRAL_CLIENT_INSTANCE is None:
        MISTRAL_CLIENT_INSTANCE = MistralAsyncClient(api_key=settings.mistral_api_key)
    return MISTRAL_CLIENT_INSTANCE

async def analyze_candidate(clean_text: str, raw_text_for_ref: str, email_meta: dict = None) -> ExtractedApplicationData:
    if not email_meta: email_meta = {}
    
    # Session Position Resolution
    position_ref = email_meta.get("PositionReference")
    position_desc = email_meta.get("PositionDescription")
    
    if not position_ref:
        match = REF_RE.search(raw_text_for_ref)
        if match:
            extracted_ref = match.group(1).upper()
            try:
                session_info = await fetch_session_by_reference(extracted_ref)
                position_ref = session_info["reference"]
                position_desc = session_info["description"]
            except Exception:
                position_ref = extracted_ref
                position_desc = "Description not found"
        else:
            position_ref = "DEFAULT_SESSION"
            position_desc = "Session par default (non trouvee dans le mail)"

    institutions = await fetch_all_institutions()
    study_levels = await fetch_all_study_levels()
    inst_str = "\\n".join([f"ID: {i['InstitutionID']} - Label: {i['Name']}" for i in institutions])
    sl_str = "\\n".join([f"ID: {sl['StudyLevelID']} - Label: {sl['Name']}" for sl in study_levels])

    prompt = f"""
Extrayez les informations du CV en un objet JSON très strict.

REGLES CRITIQUES (LLMOps) :
1. COMPETENCES (SKILLS): Vous DEVEZ scanner tout le CV. Si un candidat liste des technologies dans la description d'un stage ou d'un projet (comme "Développement en C# et .NET"), vous DEVEZ extraire "C#" et ".NET" et les ajouter dans le tableau "skills".
2. EXPERIENCES: Récupérez TOUTES les expériences, dont les stages. Dans le champ "ExperienceDescription", listez les missions exactes ET SURTOUT les technos utilisées. Ne mettez jamais de chaines comme "Unknown", utilisez explicitement le type natif `null` (sans guillemets) si aucune valeur n'est trouvée.
3. ANNEES D'EXPERIENCE: Calculez le total des années d'expérience (ex: 2.5), incluez les stages.

MODELE DE SORTIE JSON ATTENDU :
{{
  "candidate": {{
    "ApplicationEmail": "email ou null",
    "ApplicationCandidateName": "nom ou null",
    "ApplicationCandidatePhone1": "phone ou null",
    "ApplicationCandidateAddress": "adresse ou null",
    "ApplicationCandidateBirthDate": "YYYY-MM-DD ou null"
  }},
  "skills": ["C#", ".NET", "Python"],
  "experiences": [
    {{
      "ExperienceStartDate": "YYYY-MM",
      "ExperienceEndDate": "YYYY-MM",
      "ExperienceCompany": "societe",
      "ExperiencePosition": "titre du poste",
      "ExperienceDescription": "Missions et technos"
    }}
  ],
  "degrees": [
    {{
      "DegreeObtentionYear": "YYYY",
      "Description": "titre",
      "institution_id": 1,
      "study_level_id": 1
    }}
  ],
  "total_years_experience": 0.5
}}
Remarque : Mettez la primitive JSON `null` au lieu d'une valeur string lorsqu'un champ (comme institution_id ou ExperienceStartDate) n'est pas précisé dans le CV.

Available Institutions:
{inst_str}

Available Study Levels:
{sl_str}

CV Text:
{clean_text}
"""

    try:
        client = get_mistral_client()
        response = await client.chat(
            model="mistral-small-latest",
            messages=[ChatMessage(role="user", content=prompt)],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        extracted_json = json.loads(response.choices[0].message.content)
        
        def safe_val(val):
            if isinstance(val, str) and val.strip().lower() in ("null", "none", "unknown", "inconnu", ""):
                return None
            return val
        
        candidate_data = extracted_json.get("candidate", {})
        candidate = Candidate(
            ApplicationEmail=safe_val(candidate_data.get("ApplicationEmail")) or email_meta.get("email") or "unknown@email.com",
            ApplicationCandidateName=safe_val(candidate_data.get("ApplicationCandidateName")) or email_meta.get("name") or "Candidat Anonyme",
            ApplicationCandidatePhone1=safe_val(candidate_data.get("ApplicationCandidatePhone1")),
            ApplicationCandidateAddress=safe_val(candidate_data.get("ApplicationCandidateAddress")),
            ApplicationCandidateBirthDate=safe_val(candidate_data.get("ApplicationCandidateBirthDate")),
        )
        
        skills_list = [Skill(SkillDescription=s) for s in extracted_json.get("skills", [])]
        
        experiences_list = []
        for exp in extracted_json.get("experiences", []):
            experiences_list.append(Experience(
                ExperienceStartDate=safe_val(exp.get("ExperienceStartDate")),
                ExperienceEndDate=safe_val(exp.get("ExperienceEndDate")),
                ExperienceCompany=safe_val(exp.get("ExperienceCompany")),
                ExperiencePosition=safe_val(exp.get("ExperiencePosition")),
                ExperienceDescription=safe_val(exp.get("ExperienceDescription"))
            ))
            
        degrees_list = []
        for deg in extracted_json.get("degrees", []):
            degrees_list.append(ApplicationDegree(
                DegreeObtentionYear=safe_val(deg.get("DegreeObtentionYear")),
                Description=safe_val(deg.get("Description")),
                institution_id=safe_val(deg.get("institution_id")),
                study_level_id=safe_val(deg.get("study_level_id"))
            ))
            
        total_years = extracted_json.get("total_years_experience", 0.0)
            
    except Exception as e:
        # Fallback in case Mistral API fails or returns invalid JSON
        import traceback
        print(f"Mistral extraction failed: {e}")
        traceback.print_exc()
        candidate = Candidate(
            ApplicationEmail=email_meta.get("email") or "unknown@email.com",
            ApplicationCandidateName=email_meta.get("name") or "Candidat Anonyme",
        )
        skills_list = []
        experiences_list = []
        degrees_list = []

    extracted_data = ExtractedApplicationData(
        candidate=candidate,
        skills=skills_list,
        experiences=experiences_list,
        degrees=degrees_list,
        total_years_experience=total_years if 'total_years' in locals() else 0.0,
        session_position_reference=position_ref,
        session_position_description=position_desc
    )
    
    return extracted_data
