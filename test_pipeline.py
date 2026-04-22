import json
import os
import sys

from ai_service.ingestion.read_db import fetch_pending_applications
from ai_service.ingestion.read_email import ingest_from_local_folders
from ai_service.processing.file_handler import process_file
from ai_service.processing.cleaner import clean_text
from ai_service.ai.analyzer import analyze_candidate
from ai_service.ai.scorer import compute_score
from ai_service.database.updater import update_application_score, insert_new_candidate_and_application

# ==== PIPELINE BDD & EMAIL LOCAL ====
def run_global_pipeline():
    print("*" * 60)
    print("====== GLOBAL PIPELINE EXECUTION =======")
    print("*" * 60 + "\n")
    
    # 1. Ingestion
    print("[ETAPE 1] - Ingestion depuis la BDD et les Emails...")
    db_apps = []
    try:
        db_apps = fetch_pending_applications()
    except Exception:
        print("Mock: DB ingestion skipped")
        
    email_apps = ingest_from_local_folders("emails")
    
    all_apps = db_apps + email_apps
    print(f"-> Trouve {len(db_apps)} candidatures en Base (pending).")
    print(f"-> Trouve {len(email_apps)} emails de candidatures locaux.\n")

    required_skills = ["python", "sql", "docker", "fastapi"]

    # 2 -> 6
    for idx, app in enumerate(all_apps, start=1):
        source = "BASE DE DONNEES" if "ApplicationID" in app else "EMAIL LOCAL"
        email_or_id = app.get("email") or app.get("sender") or app.get("ApplicationID")
        
        print(f"\n{'='*55}")
        print(f"[{idx}/{len(all_apps)}] Traitement Candidat ({source}) - [{email_or_id}]")
        print(f"{'='*55}")
        
        raw_text = app.get("subject", "") + " " + app.get("body", "")
        cv_path = app.get("pdf_path") or app.get("attachment_path")
        
        if cv_path and os.path.exists(cv_path):
            print(f"[+] CV Trouve: {cv_path}")
            raw_text += " " + process_file(cv_path)
        else:
            print(f"[-] Pas de CV physique trouve pour {cv_path}.")
            
        cleaned_text = clean_text(raw_text)
        
        print(f"[+] Analyse NLP et Rapprochement BDD en cours...")
        
        # Pydantic Model Returned
        ai_data = analyze_candidate(cleaned_text, raw_text, app)
        
        # Conversion Pydantic to Dict pour l'affichage console propre
        data_dict = ai_data.model_dump()
        
        print("\n" + "-" * 30 + " VISUALISATION " + "-" * 30)
        print(f"-> Candidat    : {data_dict['candidate']['ApplicationCandidateName']}")
        print(f"-> Email       : {data_dict['candidate']['ApplicationEmail']}")
        print(f"-> Telephone   : {data_dict['candidate']['ApplicationCandidatePhone1']}")
        print(f"-> Reference   : {data_dict['session_position_reference']}")
        print(f"-> Description : {data_dict['session_position_description']}")
        print(f"-> Competences : {[s['SkillDescription'] for s in data_dict['skills']]}")
        print("-" * 75 + "\n")
        
        # Scoring
        string_skills_only = [s.SkillDescription for s in ai_data.skills]
        score_result = compute_score(string_skills_only, required_skills)
        score = score_result["score"]
        
        print(f"[*] Score Preselection IA : {score}% (Prérequis : {required_skills})")
        print(f"[*] Explication du système  : {score_result['summary']}")
        
        # DB Update ou Insert selon la source
        app_id = app.get("ApplicationID")
        if app_id:
            # S'il vient de la BD, on met à jour le score existant
            update_application_score(app_id, score)
        else:
            # S'il vient des emails et n'est pas encore en BD, on l'y insère
            print(f"[*] Tentative de sauvegarde du Candidat Email en Base de Données...")
            insert_new_candidate_and_application(ai_data, score)

    print("\n[SUCCES] Fin du pipeline global !")

if __name__ == "__main__":
    run_global_pipeline()
