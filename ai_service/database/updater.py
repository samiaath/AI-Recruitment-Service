from .db_connection import get_db_connection

def insert_new_candidate_and_application(ai_data, score: float, explanation: str, session_pos_id: int = None, cv_path: str = None):
    """
    Insere un candidat s'il n'existe pas, puis insere son Application
    avec le score obtenu, le résumé de l'évaluation, et lie cette candidature a la SessionPosition dynamique.
    Insere egalement la piece jointe (le CV) dans la table Attachment.
    """
    conn = get_db_connection()
    if not conn:
        print(f"Mock inserting DB for app {ai_data.candidate.ApplicationEmail}")
        return None

    try:
        cursor = conn.cursor()

        email = ai_data.candidate.ApplicationEmail[:50] if ai_data.candidate.ApplicationEmail else "unknown@email.com"
        name = ai_data.candidate.ApplicationCandidateName[:50] if ai_data.candidate.ApplicationCandidateName else "Unknown"
        birthdate = ai_data.candidate.ApplicationCandidateBirthDate[:15] if ai_data.candidate.ApplicationCandidateBirthDate else None
        phone1 = ai_data.candidate.ApplicationCandidatePhone1[:20] if ai_data.candidate.ApplicationCandidatePhone1 else None
        phone2 = ai_data.candidate.ApplicationCandidatePhone2[:20] if ai_data.candidate.ApplicationCandidatePhone2 else None
        address = ai_data.candidate.ApplicationCandidateAddress[:50] if ai_data.candidate.ApplicationCandidateAddress else None

        # 1. Verifier ou inserer Candidat
        cursor.execute("SELECT CandidateID FROM Candidate WHERE ApplicationEmail = ?", (email,))
        row = cursor.fetchone()
        if row:
            candidate_id = row[0]
            print(f"[BDD] Candidat existant trouve (ID: {candidate_id})")      
        else:
            cursor.execute("""
                INSERT INTO Candidate (ApplicationEmail, ApplicationCandidateName, ApplicationCandidateBirthDate, ApplicationCandidatePhone1, ApplicationCandidatePhone2, ApplicationCandidateAddress)
                OUTPUT INSERTED.CandidateID
                VALUES (?, ?, ?, ?, ?, ?)
            """, (email, name, birthdate, phone1, phone2, address))
            candidate_id = cursor.fetchone()[0]
            print(f"[BDD] Nouveau Candidat cree (ID: {candidate_id})")        

        # 2. Utilisation du `session_pos_id` passe dynamiquement depuis le main.py 
        # (Qui a lui meme fait la requete 'fetch_session_by_reference' exacte ou via DefaultSession)
        if not session_pos_id and ai_data.session_position_reference and ai_data.session_position_reference != "DEFAULT_SESSION" and ai_data.session_position_reference != "FALLBACK":
            cursor.execute("SELECT SessionPositionID FROM SessionPosition WHERE PositionReference = ?", (ai_data.session_position_reference,))
            sp_row = cursor.fetchone()
            if sp_row:
                session_pos_id = sp_row[0]

        # 3. Inserer la nouvelle Application
        cursor.execute("""
            INSERT INTO Application (
                ApplicationReceiptDate,
                ApplicationStatus,
                ApplicationCandidateID,
                ApplicationSessionPositionID,
                ApplicationPreselectionScore,
                ApplicationEvaluationExplanation,
                status_ai
            )
            OUTPUT INSERTED.ApplicationID
            VALUES (GETDATE(), 1, ?, ?, ?, ?, 'done')
        """, (candidate_id, session_pos_id, score, explanation))

        app_row = cursor.fetchone()
        
        if app_row:
            app_id = app_row[0]
            print(f"[BDD] Nouvelle Application inseree avec succes (ApplicationID: {app_id}) - Liee a la SessionPositionID {session_pos_id}")
            
            # Insert Attachment
            if cv_path:
                import os
                import uuid
                filename = os.path.basename(cv_path)[:100]
                attachment_ref = str(uuid.uuid4())[:100]
                
                cursor.execute("""
                    INSERT INTO Attachment (
                        AttachmentTitle, AttachmentType, AttachmentReferenceGuid, AttachmentApplicationID
                    ) VALUES (?, 'CV', ?, ?)
                """, (filename, attachment_ref, app_id))
                print(f"[BDD] Piece jointe '{filename}' liee avec succes a l'ApplicationID {app_id}")

            conn.commit()
            return app_id
            
        conn.commit()
        return None

    except Exception as e:
        print(f"[Erreur] DB Insert failed: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def update_application_score(application_id, score: float, explanation: str):
    conn = get_db_connection()
    if not conn:
        print(f"Mock updating DB for app {application_id} to score {score}")    
        return

    try:
        cursor = conn.cursor()
        query = """
            UPDATE Application
            SET
                ApplicationPreselectionScore = ?,
                ApplicationEvaluationExplanation = ?,
                status_ai = 'done'
            WHERE ApplicationID = ?
        """
        cursor.execute(query, (score, explanation, application_id))
        conn.commit()
        print(f"Updated application {application_id} with score {score}")       
    except Exception as e:
        print(f"DB Update failed: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
