import os
import json
import asyncio
from docx import settings
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
from collections import defaultdict

_CANDIDATE_LOCKS = defaultdict(asyncio.Lock)

_SEMAPHORE = None
def get_semaphore():
    global _SEMAPHORE
    from .config import settings
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(settings.pipeline_concurrency)
    return _SEMAPHORE


def _mark_metadata_done(meta_path: str) -> None:
    """
    Passe le statut d'un metadata.json d'email à 'done' (lecture + écriture).
    Fonction synchrone volontairement isolée : appelée via asyncio.to_thread
    pour ne pas bloquer la boucle asyncio avec des I/O fichier.
    """
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["status"] = "done"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)

async def process_single_application(app_data):
    lock_key = (
        app_data.get("email") or 
        app_data.get("ApplicationEmail") or 
        app_data.get("ApplicationID")
    )
    
    # Optional: if no key is found, default to a random uuid to not lock everything
    if not lock_key:
        import uuid
        lock_key = str(uuid.uuid4())
        
    async with _CANDIDATE_LOCKS[lock_key]:
        async with get_semaphore():
            # 1. Extraction de la Description Metier pour le Matching
            source = app_data.get("source") # "db" (depuis DB) ou sinon "email"
            
            session_data = {}
            # A. Cas Base de Donnee : 'PositionDescription' a deja ete recuperee au depart.
            if source == "db" and app_data.get("PositionDescription"):
                description_poste = app_data["PositionDescription"]
            # B. Cas Email : On connait juste le subject/body, il faut faire la requete SQL
            else:
                # Essaye d'identifier la reference dans les metadata local de l'email
                subject_ref = app_data.get("job_reference", "")
                
                raw_text_temp = app_data.get("subject", "") + " " + app_data.get("body", "")
                all_refs = await fetch_all_session_references()
                for ref in all_refs:
                    if ref and ref in raw_text_temp:
                        subject_ref = ref
                        break

                # Va requeter la DB (via EXACT MATCH ou SessionDefault=1 si introuvable)
                session_data = await fetch_session_by_reference(subject_ref)
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
                raw_text += " " + await process_file(cv_path)
                
            cleaned_text = clean_text(raw_text)
            ai_extracted = await analyze_candidate(cleaned_text, raw_text, app_data)
            
            # Surcharger les informations du JSON avec les véritables valeurs trouvées en base de données
            if source == "db":
                ai_extracted.session_position_reference = app_data.get("PositionReference", "")
            else:
                ai_extracted.session_position_reference = session_data.get("reference", "")
                
            ai_extracted.session_position_description = description_poste
            
            # 3. Calcul de Notation Dynamique par LLM (En fonction de SessionPosition.Description !)
            score_result = await compute_score(ai_extracted, description_poste)
            score = score_result["score"]
            
            # 4. Injection et Mise a jour DB
            app_id = app_data.get("ApplicationID")
            explanation = score_result["summary"]
            
            if app_id:
                # DB = Mise a jour
                await update_application_score(app_id, score, explanation, ai_extracted)
            else:
                # EMAIL = Insertion Nouvelle
                from .database.updater import insert_new_candidate_and_application
                # On lie SessionPositionID trouve dynamiquement !
                session_pos_id = app_data.get("SessionPositionID") 
                app_id = await insert_new_candidate_and_application(ai_extracted, score, explanation, session_pos_id, cv_path)
                
                folder_path = app_data.get("folder_path")
                if folder_path and os.path.exists(os.path.join(folder_path, "metadata.json")):
                    meta_path = os.path.join(folder_path, "metadata.json")
                    # Lecture/écriture fichier = opération bloquante : on la déporte dans
                    # un thread pour ne pas geler la boucle asyncio (comme les accès DB).
                    await asyncio.to_thread(_mark_metadata_done, meta_path)
            
            # Consolider le JSON final pour Swagger UI (complet)
            full_result = ai_extracted.dict()
            full_result["ApplicationPreselectionScore"] = score
            full_result["ApplicationEvaluationExplanation"] = explanation
            
            if isinstance(app_id, str) and app_id.startswith("Erreur SQL:"):
                full_result["DATABASE_INSERTION_ERROR"] = app_id

            
            return full_result

async def run_pipeline_logic():
    """
    FONCTION CENTRALE :
    Traite toutes les candidatures en se basant sur le Reference et Description de SessionPosition.
    """
    apps_db = await fetch_pending_applications()
    apps_email = ingest_from_local_folders("emails")
    all_apps = apps_db + apps_email
    
    results = await asyncio.gather(*(process_single_application(app) for app in all_apps))
        
    return {"status": "success", "processed": len(results), "details": results}

async def pipeline_cron():
    print("[CRON] Pause initiale de 5 minutes pour tester manuellement via Swagger UI (/docs).")
    await asyncio.sleep(300) # Attente de 5 minutes au démarrage
    while True:
        try:
            print("[CRON] Debut du scan de l'Inbox Email...")
            await fetch_new_emails()
            print("[CRON] Demarrage du traitement Pipeline avec Match Dynamique (Emails + DB)...")
            result = await run_pipeline_logic()
            print(f"[CRON] Pipeline termine : {result['processed']} candidatures traitees avec succes.")
        except Exception as e:
            print(f"[CRON] Erreur tache de fond : {e}")
        await asyncio.sleep(int(settings.cron_interval_hours * 3600))

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("AI Service - Starting up!")
    cron_task = asyncio.create_task(pipeline_cron())
    yield
    print("AI Service - Shutting down!")
    cron_task.cancel()

app = FastAPI(
    title="AI Recruitment Service", 
    description="API for the AI Recruitment internal services, including pipeline management, test executions, and monitoring.",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/pipeline/run", tags=["Pipeline"], summary="Run global pipeline manually")
async def trigger_pipeline():
    """
    Trigger the main recruitment pipeline manually to process pending database applications and emails.
    """
    print("[MANUEL] Requête reçue via Swagger UI. Scan de l'Inbox Email...")
    await fetch_new_emails()
    print("[MANUEL] Démarrage du traitement Pipeline...")
    return await run_pipeline_logic()

@app.post("/tests/test-pipeline", tags=["Tests"], summary="Run the CLI test pipeline script")
async def run_test_pipeline():
    """
    Executes the overall test pipeline script (`test_pipeline.py`) which processes all items and outputs to console.
    Returns status of the execution.
    """
    import sys
    import os
    # Add root to sys.path if not present to import test_pipeline
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_dir not in sys.path:
        sys.path.append(root_dir)
        
    import test_pipeline
    await test_pipeline.run_global_pipeline()
    return {"status": "success", "message": "Test pipeline executed successfully. Check console for logs."}

@app.post("/tests/unit-tests", tags=["Tests"], summary="Run all unit tests")
async def run_unit_tests():
    """
    Run all automated unit tests located in the `tests/` folder using Python's unittest module or pytest.
    """
    import subprocess
    import os
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        # Run pytest if installed, else fallback to unittest
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/"], 
            cwd=root_dir, 
            capture_output=True, 
            text=True
        )
        if result.returncode == 0:
            return {"status": "success", "output": result.stdout}
        else:
            return {"status": "failed", "output": result.stdout, "errors": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Hôte/port configurables via variables d'environnement.
    # Par défaut on écoute en local (127.0.0.1) — plus sûr. En conteneur, le
    # Dockerfile lance uvicorn avec --host 0.0.0.0 explicitement (réseau Docker),
    # ou bien on positionne API_HOST=0.0.0.0 pour un déploiement serveur.
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("ai_service.main:app", host=host, port=port, reload=True)
