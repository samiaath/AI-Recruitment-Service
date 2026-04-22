import os
import asyncio
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager

from .ingestion.read_db import fetch_pending_applications, fetch_session_by_reference, fetch_all_session_references
from .ingestion.read_email import ingest_from_local_folders, fetch_new_emails
from .processing.file_handler import process_file
from .processing.cleaner import clean_text
from .ai.analyzer import analyze_candidate
from .ai.scorer import compute_score
from .database.updater import update_application_score

def run_pipeline_logic():
    """
    FONCTION CENTRALE :
    Traite toutes les candidatures en se basant sur le Reference et Description de SessionPosition.
    """
    apps_db = fetch_pending_applications()
    apps_email = ingest_from_local_folders("emails")
    all_apps = apps_db + apps_email
    
    results = []
    
    for app_data in all_apps:
        # 1. Extraction de la Description Metier pour le Matching
        source = app_data.get("source") # "db" (depuis DB) ou sinon "email"
        
        # A. Cas Base de Donnee : 'PositionDescription' a deja ete recuperee au depart.
        if source == "db" and app_data.get("PositionDescription"):
            description_poste = app_data["PositionDescription"]
        # B. Cas Email : On connait juste le subject/body, il faut faire la requete SQL
        else:
            # Essaye d'identifier la reference dans les metadata local de l'email
            subject_ref = app_data.get("job_reference", "")
            
            raw_text_temp = app_data.get("subject", "") + " " + app_data.get("body", "")
            all_refs = fetch_all_session_references()
            for ref in all_refs:
                if ref and ref in raw_text_temp:
                    subject_ref = ref
                    break

            # Va requeter la DB (via EXACT MATCH ou SessionDefault=1 si introuvable)
            session_data = fetch_session_by_reference(subject_ref)
            description_poste = session_data.get("description", "")
            # On stock l'ID de session recuperee pour pouvoir relier l'Email correctement a la table Application
            app_data["SessionPositionID"] = session_data.get("id")

        # Split la Description du SQL en mots-cles simples (enlever ponctuation) pour le matcher SpaCy
        required_skills = [word.strip() for word in description_poste.split() if len(word) > 3]
        if not required_skills:
            required_skills = ["compétence", "profil", "expérience"] # Fallback pure NLP

        # 2. Lecture des pieces jointes
        raw_text = app_data.get("subject", "") + " " + app_data.get("body", "")
        cv_path = app_data.get("pdf_path") or app_data.get("attachment_path")
        
        if cv_path and os.path.exists(cv_path):
            raw_text += " " + process_file(cv_path)
            
        cleaned_text = clean_text(raw_text)
        ai_extracted = analyze_candidate(cleaned_text, raw_text, app_data)
        
        # Surcharger les informations du JSON avec les véritables valeurs trouvées en base de données
        if source == "db":
            ai_extracted.session_position_reference = app_data.get("PositionReference", "")
        else:
            ai_extracted.session_position_reference = session_data.get("reference", "")
            
        ai_extracted.session_position_description = description_poste
        
        # 3. Calcul de Notation Dynamique ! (En fonction de SessionPosition.Description !)
        string_skills_only = [s.SkillDescription for s in ai_extracted.skills]
        score_result = compute_score(string_skills_only, description_poste)
        score = score_result["score"]
        
        # 4. Injection et Mise a jour DB
        app_id = app_data.get("ApplicationID")
        explanation = score_result["summary"]
        
        if app_id:
            # DB = Mise a jour
            update_application_score(app_id, score, explanation)
        else:
            # EMAIL = Insertion Nouvelle
            from .database.updater import insert_new_candidate_and_application
            # On lie SessionPositionID trouve dynamiquement !
            session_pos_id = app_data.get("SessionPositionID") 
            app_id = insert_new_candidate_and_application(ai_extracted, score, explanation, session_pos_id, cv_path)
            
            folder_path = app_data.get("folder_path")
            if folder_path and os.path.exists(os.path.join(folder_path, "metadata.json")):
                import json
                meta_path = os.path.join(folder_path, "metadata.json")
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["status"] = "done"  
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=4, ensure_ascii=False)
        
        # Consolider le JSON final pour Swagger UI (complet)
        full_result = ai_extracted.dict()
        full_result["ApplicationPreselectionScore"] = score
        full_result["ApplicationEvaluationExplanation"] = explanation
        
        results.append(full_result)
        
    return {"status": "success", "processed": len(results), "details": results}

async def pipeline_cron():
    print("[CRON] Pause initiale de 5 minutes pour vous laisser le temps de tester manuellement via Swagger UI (/docs).")
    await asyncio.sleep(300) # Attente de 5 minutes au démarrage
    while True:
        try:
            print("[CRON] Debut du scan de l'Inbox Email...")
            await asyncio.to_thread(fetch_new_emails)
            print("[CRON] Demarrage du traitement Pipeline avec Match Dynamique (Emails + DB)...")
            result = await asyncio.to_thread(run_pipeline_logic)
            print(f"[CRON] Pipeline termine : {result['processed']} candidatures traitees avec succes.")
        except Exception as e:
            print(f"[CRON] Erreur tache de fond : {e}")
        await asyncio.sleep(4 * 60 * 60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("AI Service - Starting up!")
    cron_task = asyncio.create_task(pipeline_cron())
    yield
    print("AI Service - Shutting down!")
    cron_task.cancel()

app = FastAPI(title="AI Recruitment Service", lifespan=lifespan)

@app.post("/pipeline/run")
def trigger_pipeline():
    print("[MANUEL] Requête reçue via Swagger UI. Scan de l'Inbox Email...")
    fetch_new_emails()
    print("[MANUEL] Démarrage du traitement Pipeline...")
    return run_pipeline_logic()

if __name__ == "__main__":
    uvicorn.run("ai_service.main:app", host="0.0.0.0", port=8000, reload=True)
