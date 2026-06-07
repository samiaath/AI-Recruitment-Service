import json
import os
import asyncio
import sys

# Ajouter le dossier parent au PATH pour pouvoir importer 'ai_service'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_service.ingestion.read_db import fetch_pending_applications, fetch_session_by_reference
from ai_service.processing.file_handler import process_file
from ai_service.processing.cleaner import clean_text
from ai_service.ai.analyzer import analyze_candidate
from ai_service.ai.scorer import compute_score

async def run_db_extraction_pipeline():
    print("=== Démarrage du Pipeline : Extraction des CVs DB 'pending' ===")
    
    # Ingestion depuis la base de données
    print("\n[1] Recherche des candidatures 'pending' dans la base de données...")
    db_apps = await fetch_pending_applications()
    
    if not db_apps:
        print("Aucune candidature en attente d'analyse pour le moment dans la DB.")
        return

    print(f"-> {len(db_apps)} candidature(s) prête(s) à être analysée(s).")
    results_list = []

    for idx, app in enumerate(db_apps, start=1):
        print(f"\n--- Traitement Candidat {idx}/{len(db_apps)} ---")
        
        subject_ref = app.get("PositionReference", "")
        description_poste = app.get("PositionDescription", "")
        session_pos_id = app.get("SessionPositionID")
        
        try:
            session_data = await fetch_session_by_reference(subject_ref)
            if not description_poste:
                description_poste = session_data.get("description", "")
            if not session_pos_id:
                session_pos_id = session_data.get("id")
            reference_trouvee = session_data.get("reference", subject_ref)
        except Exception as e:
            reference_trouvee = subject_ref
            print(f"Erreur DB fetch session fallback: {e}")

        raw_text = f"Nom: {app.get('name', '')} Email: {app.get('email', '')} Téléphone: {app.get('phone', '')} "
        cv_path = app.get("attachment_path")
        
        if cv_path and os.path.exists(cv_path):
            print(f"-> Lecture du fichier CV : {os.path.basename(cv_path)}")
            raw_text += " " + await process_file(cv_path)
        else:
            print(f"-> Aucun document CV physique trouvé à l'emplacement : {cv_path}")
            
        cleaned_text = clean_text(raw_text)
        
        print("-> Analyse IA : Extraction des informations...")
        ai_data = await analyze_candidate(cleaned_text, raw_text, app)
        
        ai_data.session_position_reference = reference_trouvee
        ai_data.session_position_description = description_poste
        
        data_dict = ai_data.model_dump()
        
        print("-> IA Scorer : Évaluation du profil...")
        score_result = await compute_score(ai_data, description_poste)
        score = score_result["score"]
        explanation = score_result["summary"]
        
        print(f"[*] Score IA Obtenu : {score}%")
        
        final_record = {
            "source_folder": "database_pending",
            "cv_filename": os.path.basename(cv_path) if cv_path else "",
            "ai_extracted_data": data_dict,
            "score": score,
            "explanation": explanation,
            "session_position_id": session_pos_id,
            "target_reference": reference_trouvee, 
            "metadata_origin": {
                "source": "db",
                "application_id": app.get("ApplicationID"),
                "email": app.get("email"),
                "name": app.get("name"),
                "base_path": cv_path
            }
        }
        results_list.append(final_record)

    output_path = os.path.join(os.path.dirname(__file__), "pipeline_db_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results_list, f, indent=4, ensure_ascii=False)
        
    print(f"\n[SUCCES] L'analyse de la base de données est terminée. Données sauvées dans '{output_path}'.")

if __name__ == "__main__":
    asyncio.run(run_db_extraction_pipeline())