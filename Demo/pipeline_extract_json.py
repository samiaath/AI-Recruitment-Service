import json
import os
import asyncio
import sys

# Ajouter le dossier parent au PATH pour pouvoir importer 'ai_service'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_service.ingestion.read_db import fetch_session_by_reference, fetch_all_session_references
from ai_service.ingestion.read_email import fetch_new_emails, ingest_from_local_folders
from ai_service.processing.file_handler import process_file
from ai_service.processing.cleaner import clean_text
from ai_service.ai.analyzer import analyze_candidate
from ai_service.ai.scorer import compute_score

async def run_extraction_pipeline():
    print("=== Démarrage du Pipeline : Extraction des CVs UNSEEN ===")
    
    # Étape 1 : Connexion IMAP et téléchargement des emails "UNSEEN"
    print("\n[1] Recherche de nouveaux e-mails non lus (UNSEEN)...")
    await fetch_new_emails()
    
    # Étape 2 : Ingestion en mémoire des candidatures extraites (limitées aux 'pending')
    print("\n[2] Ingestion des dossiers locaux pour les e-mails en attente (pending)...")
    
    # On s'assure d'utiliser le dossier 'emails' à la racine du projet
    emails_dir = os.path.join(os.path.dirname(__file__), "..", "emails")
    email_apps = ingest_from_local_folders(emails_dir)
    
    if not email_apps:
        print("Aucun CV en attente d'analyse pour le moment.")
        return

    print(f"-> {len(email_apps)} CV(s) prêt(s) à être analysé(s).")
    results_list = []

    for idx, app in enumerate(email_apps, start=1):
        print(f"\n--- Traitement Candidat {idx}/{len(email_apps)} ---")
        
        # Identifier la référence de l'offre
        subject_ref = app.get("job_reference", "")
        raw_text_temp = app.get("subject", "") + " " + app.get("body", "")
        
        try:
            all_refs = await fetch_all_session_references()
            for ref in all_refs:
                if ref and ref in raw_text_temp:
                    subject_ref = ref
                    break
        except Exception as e:
            print(f"Erreur lors de la récupération des références: {e}")

        # Récupération de la description du poste en base
        try:
            session_data = await fetch_session_by_reference(subject_ref)
            description_poste = session_data.get("description", "")
            reference_trouvee = session_data.get("reference", "")
        except Exception as e:
            description_poste = ""
            reference_trouvee = ""
            print(f"Erreur DB fetch session: {e}")

        # Extraction du texte (Mail + CV)
        raw_text = app.get("subject", "") + " " + app.get("body", "")
        cv_path = app.get("pdf_path") or app.get("attachment_path")
        
        if cv_path and os.path.exists(cv_path):
            print(f"-> Lecture du fichier: {os.path.basename(cv_path)}")
            raw_text += " " + await process_file(cv_path)
        else:
            print("-> Aucun document CV physique trouvé.")
            
        cleaned_text = clean_text(raw_text)
        
        # Analyse IA avec Pydantic
        print("-> Analyse IA : Extraction des informations...")
        ai_data = await analyze_candidate(cleaned_text, raw_text, app)
        
        # Surcharges contextuelles par rapport à la base
        ai_data.session_position_reference = reference_trouvee
        ai_data.session_position_description = description_poste
        
        data_dict = ai_data.model_dump()
        
        # Scoring IA
        print("-> IA Scorer : Évaluation du profil...")
        score_result = await compute_score(ai_data, description_poste)
        score = score_result["score"]
        explanation = score_result["summary"]
        
        print(f"[*] Score IA Obtenu : {score}%")
        
        # Le point le PLUS IMPORTANT : 
        # Plutôt que de stocker un 'SessionPositionID', on stocke purement "reference_trouvee" (ex: RF001).
        # C'est le script de génération SQL qui fera une sous-requête (SELECT ID FROM... WHERE Reference = 'RF001').
        final_record = {
            "source_folder": app.get("folder_path"),
            "cv_filename": os.path.basename(cv_path) if cv_path else "",
            "ai_extracted_data": data_dict,
            "score": score,
            "explanation": explanation,
            "target_reference": reference_trouvee if reference_trouvee else "DEFAULT001",
            "metadata_origin": {
                "sender": app.get("sender"),
                "subject": app.get("subject")
            }
        }
        results_list.append(final_record)

        # Mise à jour du metadata.json local pour ne pas le retraiter la prochaine fois
        meta_file = os.path.join(app.get("folder_path", ""), "metadata.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as mf:
                    meta_data = json.load(mf)
                meta_data["status"] = "done"
                with open(meta_file, "w", encoding="utf-8") as mf:
                    json.dump(meta_data, mf, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"Erreur lors de la mise à jour du status pour {meta_file}: {e}")

    # Exportation finale en JSON
    output_path = os.path.join(os.path.dirname(__file__), "pipeline_json_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results_list, f, indent=4, ensure_ascii=False)
        
    print(f"\n[SUCCES] L'analyse de contenu métier est terminée. Données sauvées dans '{output_path}'.")

if __name__ == "__main__":
    asyncio.run(run_extraction_pipeline())
