from ..database.db_connection import get_db_connection

def fetch_pending_applications() -> list:
    conn = get_db_connection()
    if not conn:
        return []

    applications = []
    try:
        cursor = conn.cursor()
        query = """
            SELECT
                a.ApplicationID,
                sp.PositionReference,
                sp.Description as PositionDescription,
                att.AttachmentTitle,
                c.ApplicationEmail,
                c.ApplicationCandidateName,
                c.ApplicationCandidatePhone1,
                sp.SessionPositionID
            FROM Application a
            LEFT JOIN SessionPosition sp ON a.ApplicationSessionPositionID = sp.SessionPositionID
            LEFT JOIN Attachment att ON a.ApplicationID = att.AttachmentApplicationID AND att.AttachmentType = 'CV'
            LEFT JOIN Candidate c ON a.ApplicationCandidateID = c.CandidateID   
            WHERE a.status_ai = 'pending'
        """
        cursor.execute(query)
        for row in cursor.fetchall():
            cv_path = f"CVs/{row[3]}" if row[3] else None

            applications.append({
                "ApplicationID": row[0],
                "PositionReference": row[1],
                "PositionDescription": row[2] if row[2] else "",
                "SessionPositionID": row[7],
                "attachment_path": cv_path,
                "email": row[4],
                "name": row[5],
                "phone": row[6],
                "source": "db"
            })
    except Exception as e:
        print(f"Error fetching from DB: {e}")
    finally:
        if conn:
            conn.close()

    return applications

def fetch_session_by_reference(ref: str) -> dict:
    """
    Tente de trouver la SessionPosition via sa reference (PositionReference).
    Si on ne trouve rien (ou si ref est vide), on fait un 'fallback' vers
    la Session active par defaut (SessionDefault = 1).
    """
    fallback_desc = ""
    fallback_ref = "DEFAULT"
    fallback_id = None

    conn = get_db_connection()
    if not conn:
        return {"id": None, "reference": ref, "description": ""}

    try:
        cursor = conn.cursor()
        
        # 1. Chercher par reference exacte (si fournie)
        if ref and ref.strip() != "":
            cursor.execute("SELECT SessionPositionID, PositionReference, Description FROM SessionPosition WHERE PositionReference = ?", (ref,))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "reference": row[1], "description": row[2] if row[2] else ""}

        # 2. MATCH FALLBACK : Trouver la session par defaut (SessionDefault = 1)
        query_default = """
            SELECT TOP 1 sp.SessionPositionID, sp.PositionReference, sp.Description
            FROM SessionPosition sp
            JOIN Session s ON sp.SessionID = s.SessionID
            WHERE s.SessionDefault = 1
        """
        cursor.execute(query_default)
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "reference": row[1], "description": row[2] if row[2] else "Description de poste non trouvee, session par defaut."}

    except Exception as e:
        print(f"Error fetch session (read_db) : {e}")
    finally:
        if conn:
            conn.close()

    return {"id": fallback_id, "reference": fallback_ref, "description": fallback_desc}

def fetch_all_session_references() -> list:
    conn = get_db_connection()
    if not conn:
        return []
    
    references = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT PositionReference FROM SessionPosition WHERE PositionReference IS NOT NULL")
        for row in cursor.fetchall():
            references.append(row[0])
    except Exception as e:
        print(f"Error fetching references: {e}")
    finally:
        if conn:
            conn.close()
            
    return references
