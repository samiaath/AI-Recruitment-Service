import json
import os
import sys

from ai_service.ingestion.read_db import fetch_pending_applications, fetch_session_by_reference, fetch_all_session_references
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
    print("[ETAPE 1] - Ingestion depuis les Emails IMAP...")
    try:
        from ai_service.ingestion.read_email import fetch_new_emails
        fetch_new_emails()
    except Exception as e:
        print(f"Erreur IMAP : {e}")
        
    print("[ETAPE 2] - Ingestion depuis la BDD et locaux...")
    db_apps = []
    try:
        db_apps = fetch_pending_applications()
    except Exception:
        print("Mock: DB ingestion skipped")
        
    email_apps = ingest_from_local_folders("emails")
    
    all_apps = db_apps + email_apps
    print(f"-> Trouve {len(db_apps)} candidatures en Base (pending).")
    print(f"-> Trouve {len(email_apps)} emails de candidatures locaux.\n")

    # 2 -> 6
    for idx, app in enumerate(all_apps, start=1):
        source = app.get("source", "db" if "ApplicationID" in app else "email")
        source_print = "BASE DE DONNEES" if source == "db" else "EMAIL LOCAL"
        email_or_id = app.get("email") or app.get("sender") or app.get("ApplicationID")
        
        print(f"\n{'='*55}")
        print(f"[{idx}/{len(all_apps)}] Traitement Candidat ({source_print}) - [{email_or_id}]")
        print(f"{'='*55}")
        
        # 1. Extraction de la Description Metier pour le Matching
        if source == "db" and app.get("PositionDescription"):
            description_poste = app["PositionDescription"]
        else:
            # Essaye d'identifier la reference dans les metadata local de l'email
            subject_ref = app.get("job_reference", "")
            raw_text_temp = app.get("subject", "") + " " + app.get("body", "")
            all_refs = fetch_all_session_references()
            for ref in all_refs:
                if ref and ref in raw_text_temp:
                    subject_ref = ref
                    break

            session_data = fetch_session_by_reference(subject_ref)
            description_poste = session_data.get("description", "")
            app["SessionPositionID"] = session_data.get("id")

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
        
        # Surcharger les informations du JSON avec les véritables valeurs trouvées en base de données
        if source == "db":
            ai_data.session_position_reference = app.get("PositionReference", "")
        else:
            ai_data.session_position_reference = session_data.get("reference", "")
            
        ai_data.session_position_description = description_poste
        
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
        
        # 3. Calcul de Notation Dynamique ! (En fonction de SessionPosition.Description !)
        string_skills_only = [s.SkillDescription for s in ai_data.skills]
        score_result = compute_score(string_skills_only, description_poste)
        score = score_result["score"]
        explanation = score_result["summary"]
        
        print(f"[*] Score Preselection IA : {score}%")
        print(f"[*] Explication du système  : {explanation}")
        
        # 4. Injection et Mise a jour DB
        app_id = app.get("ApplicationID")
        
        if app_id:
            # DB = Mise a jour
            update_application_score(app_id, score, explanation)
        else:
            # EMAIL = Insertion Nouvelle
            print(f"[*] Tentative de sauvegarde du Candidat Email en Base de Données...")
            session_pos_id = app.get("SessionPositionID") 
            insert_new_candidate_and_application(ai_data, score, explanation, session_pos_id, cv_path)
            
            folder_path = app.get("folder_path")
            if folder_path and os.path.exists(os.path.join(folder_path, "metadata.json")):
                meta_path = os.path.join(folder_path, "metadata.json")
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["status"] = "done"  
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=4, ensure_ascii=False)

    print("\n[SUCCES] Fin du pipeline global !")

if __name__ == "__main__":
    run_global_pipeline()
