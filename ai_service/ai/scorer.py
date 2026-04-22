from typing import Dict, Any
import spacy

try:
    nlp = spacy.load("fr_core_news_sm")
except Exception:
    nlp = spacy.blank("fr")

KNOWN_SKILLS = ["python", "sql", "excel", "power bi", "docker", "kubernetes", "fastapi", "pandas", "spacy", "react", "angular", "java", "c#", ".net"]

def extract_skills_from_description(description_text: str) -> list:
    """ Extrait les competences de la description SQL via NLP et KNOWN_SKILLS """
    if not description_text:
        return []
    
    doc = nlp(description_text.lower())
    found = set()
    for token in doc:
        if token.text in KNOWN_SKILLS:
            found.add(token.text)
            
    # Ajoute aussi un scan direct pour les mots-cles composes (comme power bi)
    for ks in KNOWN_SKILLS:
        if ks in description_text.lower() and ks not in found:
            found.add(ks)
            
    return list(found)

# [MOTEUR MATCHING] Calcule le POURCENTAGE (%) Profil/Offre bas sur SessionPosition.Description
def compute_score(candidate_skills: list, description_text: str) -> Dict[str, Any]:
    
    required_skills = extract_skills_from_description(description_text)
    
    if not required_skills:
        return {
            "score": 0.0,
            "matched": [],
            "missing": [],
            "summary": "Explication: La description du poste ne detaille aucune competence technique attendue de notre base de donnees NLP."
        }
        
    matched = [s for s in candidate_skills if s in required_skills]
    missing = [s for s in required_skills if s not in candidate_skills]
    bonus = [s for s in candidate_skills if s not in required_skills]
    
    score = (len(matched) / len(required_skills)) * 100
    score = round(score, 2)
    
    # Explication detaillee (Points forts et Points faibles)
    if matched:
        strengths = f"Points forts: compétence démontrée en {', '.join(matched).upper()}."
    else:
        strengths = "Points forts: Aucun alignement direct trouvé avec la description du poste."
        
    if missing:
        weaknesses = f"Points faibles: lacunes sur {', '.join(missing).upper()} (requis selon l'offre)."
    else:
        weaknesses = "Points faibles: Aucune lacune, profil parfaitement aligné."
        
    if bonus:
        bonus_text = f" Bonus détectés: {', '.join(bonus).upper()}"
    else:
        bonus_text = ""
        
    summary = f"{strengths} {weaknesses}{bonus_text}".strip()
        
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "summary": summary
    }
