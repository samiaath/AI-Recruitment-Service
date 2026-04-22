import re
import spacy
from typing import Dict, Any
from ..models import ExtractedApplicationData, Candidate, Skill
from ..ingestion.read_db import fetch_session_by_reference

try:
    nlp = spacy.load("fr_core_news_sm")
except Exception:
    nlp = spacy.blank("fr")

KNOWN_SKILLS = ["python", "sql", "excel", "power bi", "docker", "kubernetes", "fastapi", "pandas", "spacy", "react", "angular", "java", "c#", ".net"]
EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]*(?:\d[\s-]*){8,12}\d)")
REF_RE = re.compile(r"(?:ref|reference)[:\s-]*([A-Za-z0-9_-]+)", re.IGNORECASE)

# [MOTEUR NLP] Extrait Profil via SpaCy
def analyze_candidate(clean_text: str, raw_text_for_ref: str, email_meta: dict = None) -> ExtractedApplicationData:
    if not email_meta: email_meta = {}
    
    # 1. Regex sur Contact.
    # Text Extraction
    emails = EMAIL_RE.findall(clean_text)
    phones = PHONE_RE.findall(clean_text)
    
    # 2. Analyse Token SpaCy.
    doc = nlp(clean_text)
    found_skills = set()
    for token in doc:
        if token.text in KNOWN_SKILLS:
            found_skills.add(token.text)
            
    # Resolve Contact info
    contact_email = email_meta.get("email") or (emails[0] if emails else email_meta.get("sender", "unknown@email.com"))
    contact_phone = email_meta.get("phone") or (phones[0] if phones else None)
    contact_name = email_meta.get("name") or "Candidat Anonyme"
    
    # 1. Build Candidate model
    candidate = Candidate(
        ApplicationEmail=contact_email,
        ApplicationCandidateName=contact_name,
        ApplicationCandidatePhone1=contact_phone,
    )
    
    # 2. Build Skills models
    skills_list = [Skill(SkillDescription=s) for s in found_skills]
    
    # 3. Session Position Resolution (Email vs DB)
    position_ref = email_meta.get("PositionReference")
    position_desc = email_meta.get("PositionDescription")
    
    if not position_ref:
        # It's an Email input, extract via regex
        match = REF_RE.search(raw_text_for_ref)
        if match:
            extracted_ref = match.group(1).upper()
            session_info = fetch_session_by_reference(extracted_ref)
            position_ref = session_info["reference"]
            position_desc = session_info["description"]
        else:
            position_ref = "DEFAULT_SESSION"
            position_desc = "Session par default (non trouvee dans le mail)"
            

    # Extraire des dates basiques pour les experiences (ex: 2020-2022)
    import re
    years = re.findall(r'(20[0-2][0-9])', clean_text)
    
    extracted_exps = []
    if len(years) >= 2:
        extracted_exps.append({"ExperienceStartDate": years[0], "ExperienceEndDate": years[1], "ExperienceCompany": "Entreprise Extraite", "ExperiencePosition": "Employe"})
    elif len(years) == 1:
        extracted_exps.append({"ExperienceStartDate": years[0], "ExperienceEndDate": None, "ExperienceCompany": "Projet Extrait", "ExperiencePosition": "Stagiaire"})

    extracted_deg = []
    if "master" in clean_text.lower() or "ingenieur" in clean_text.lower():
        extracted_deg.append({"DegreeObtentionYear": years[0] if years else "2023", "Description": "Master / Diplome d'Ingenieur"})
    if "licence" in clean_text.lower() or "bachelor" in clean_text.lower():
        extracted_deg.append({"DegreeObtentionYear": years[-1] if years else "2020", "Description": "Licence / Bachelor"})

    from ..models import Experience, ApplicationDegree
    experiences_list = [Experience(**e) for e in extracted_exps]
    degrees_list = [ApplicationDegree(**d) for d in extracted_deg]

    # Prepare the whole Pydantic Model
    extracted_data = ExtractedApplicationData(
        candidate=candidate,
        skills=skills_list,
        experiences=experiences_list,
        degrees=degrees_list,

        session_position_reference=position_ref,
        session_position_description=position_desc
    )
    
    return extracted_data
