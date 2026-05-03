import os
import json
import imaplib
import email
from email.header import decode_header
import time
import asyncio
from ai_service.config import settings

def clean_text(text: str) -> str:
    """
    Nettoie et formate la chaine de caracteres (ex: sujet ou corps d'email).
    Supprime les retours a la ligne inutiles et les espaces superflus.
    """
    if not text:
        return ""
    return str(text).replace('\r', '').replace('\n', ' ').strip()

def get_folder_id(base_folder: str = "emails") -> str:
    """
    Genere un ID de dossier incremental (ex: 5553) pour structurer le stockage local.
    Cherche le dossier avec le numero le plus eleve et l'incremente de +1.
    """
    os.makedirs(base_folder, exist_ok=True)
    existing_ids = []
    
    # Parcourt tous les dossiers existants dans le repertoire de base
    for f in os.listdir(base_folder):
        if f.isdigit():
            existing_ids.append(int(f))
            
    # Determine le prochain identifiant disponible
    next_id = max(existing_ids) + 1 if existing_ids else 5551
    return str(next_id)

def _sync_fetch_new_emails(base_folder: str = "emails") -> int:
    """
    Connecte l'application a une boite mail via IMAP.
    - Recherche les e-mails non lus (UNSEEN).
    - Filtre par mots-cles dans l'objet (CV, candidature).
    - Telecharge les pieces jointes (PDF/Word).
    - Marque les e-mails comme lus (Seen).
    Retourne le nombre total d'e-mails acheves.
    """
    if not settings.imap_host or not settings.imap_user or not settings.imap_password:
        print("Erreur : Identifiants IMAP non configures.")
        return 0

    downloaded = 0
    try:
        # 1. Connexion securisee (SSL) au serveur IMAP
        mail = imaplib.IMAP4_SSL(settings.imap_host)
        mail.login(settings.imap_user, settings.imap_password)
        mail.select(settings.imap_folder)

        # 2. Recupere UNIQUEMENT les messages non lus
        status, response = mail.search(None, 'UNSEEN')
        if status != 'OK':
            print("Aucun message non lu trouve.")
            return 0

        message_ids = response[0].split()
        
        for msg_id in message_ids:
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # --- DECODAGE DU SUJET ---
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else 'utf-8')
                        
                    # --- FILTRAGE METIER ---
                    subject_lower = str(subject).lower()
                    mots_cles = ["candidature", "cv", "application", "postulation", "profil"]
                    if not any(mot in subject_lower for mot in mots_cles):
                        continue
                        
                    sender = msg.get("From")
                    
                    # --- EXTRACTION TEXTE CORPS ---
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            try:
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    body = part.get_payload(decode=True).decode()
                            except:
                                pass
                    else:
                        body = msg.get_payload(decode=True).decode()

                    # --- EXTRACTION DES CV (.pdf / .docx) ---
                    attachments = []
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None:
                                continue
                                
                            filename = part.get_filename()
                            if filename and (filename.lower().endswith('.pdf') or filename.lower().endswith('.docx')):
                                dec_filename, dec_enc = decode_header(filename)[0]
                                if isinstance(dec_filename, bytes):
                                    filename = dec_filename.decode(dec_enc if dec_enc else 'utf-8')
                                    
                                payload = part.get_payload(decode=True)
                                attachments.append((filename, payload))
                    
                    # --- CREATION DE METADATA (STATUT 'pending') ---
                    if attachments:
                        folder_id = get_folder_id(base_folder)
                        folder_path = os.path.join(base_folder, folder_id)
                        os.makedirs(folder_path, exist_ok=True)
                        
                        for filename, payload in attachments:
                            with open(os.path.join(folder_path, filename), "wb") as f:
                                f.write(payload)
                                
                        metadata = {
                            "id": folder_id,
                            "subject": clean_text(subject),
                            "sender": clean_text(sender),
                            "body": clean_text(body),
                            "date_received": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "pending"  # Attente de lecture IA
                        }
                        
                        with open(os.path.join(folder_path, "metadata.json"), "w", encoding="utf-8") as f:
                            json.dump(metadata, f, indent=4, ensure_ascii=False)
                            
                        downloaded += 1
                        
                        # --- MARQUAGE COMME LU ---
                        mail.store(msg_id, '+FLAGS', '\\Seen')

        mail.close()
        mail.logout()
        print(f"Telechargement termine : {downloaded} nouvel(aux) email(s) enregistre(s).")
    except Exception as e:
        print(f"Erreur IMAP: {e}")
        
    return downloaded

async def fetch_new_emails(base_folder: str = "emails") -> int:
    return await asyncio.to_thread(_sync_fetch_new_emails, base_folder)

def ingest_from_local_folders(base_folder: str = "emails") -> list:
    """
    Parcourt le stockage local (dossier 'emails/').
    Identifie toutes les candidatures au statut 'pending' dans 'metadata.json'.
    Retourne une liste de dictionnaires prets a etre envoyes a l'analyseur IA.
    """
    applications = []
    
    if not os.path.exists(base_folder):
        return applications

    for folder_name in os.listdir(base_folder):
        folder_path = os.path.join(base_folder, folder_name)
        if not os.path.isdir(folder_path):
            continue

        meta_path = os.path.join(folder_path, "metadata.json")
        if not os.path.exists(meta_path):
            continue

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        # Les e-mails "done" ont deja ete evalues
        if meta.get("status") == "done":
            continue

        # Trouve le fichier joint unique
        cv_path = None
        for file in os.listdir(folder_path):
            if file.endswith(".pdf") or file.endswith(".docx"):
                cv_path = os.path.join(folder_path, file)
                break
                
        applications.append({
            "source": "email",
            "folder_path": folder_path,
            "id": meta.get("id", folder_name),
            "subject": meta.get("subject", ""),
            "body": meta.get("body", ""),
            "sender": meta.get("sender", ""),
            "job_reference": meta.get("job_reference", ""),
            "attachment_path": cv_path
        })
        
    return applications
