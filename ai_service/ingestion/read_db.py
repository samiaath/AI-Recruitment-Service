import asyncio
from typing import Dict, Any
from ..database.db_connection import get_db_connection

# --- IN-MEMORY CACHE ---
# Cache to avoid redundant DB calls spanning multiple CVs
_CACHE: Dict[str, Any] = {
    "sessions": {},             # ref -> session_info
    "session_references": None, # list of references
    "institutions": None,       # list of dicts: {"InstitutionID": id, "Name": name}
    "study_levels": None,       # list of dicts: {"StudyLevelID": id, "Name": name}
    "default_session": None     # session_info
}
# -----------------------

def _sync_fetch_pending_applications() -> list:
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
                (SELECT TOP 1 AttachmentTitle FROM Attachment WHERE AttachmentApplicationID = a.ApplicationID AND AttachmentType = 'CV') as AttachmentTitle,
                c.ApplicationEmail,
                c.ApplicationCandidateName,
                c.ApplicationCandidatePhone1,
                sp.SessionPositionID
            FROM Application a
            LEFT JOIN SessionPosition sp ON a.ApplicationSessionPositionID = sp.SessionPositionID
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

async def fetch_pending_applications() -> list:
    return await asyncio.to_thread(_sync_fetch_pending_applications)

def _sync_fetch_session_by_reference(ref: str) -> dict:
    """
    Tente de trouver la SessionPosition via sa reference (PositionReference).
    Si on ne trouve rien (ou si ref est vide), on fait un 'fallback' vers
    la Session active par defaut (SessionDefault = 1).
    """
    fallback_desc = ""
    fallback_ref = "DEFAULT"
    fallback_id = None

    # CACHE CHECK
    if ref and ref in _CACHE["sessions"]:
        return _CACHE["sessions"][ref]

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
                session_info = {"id": row[0], "reference": row[1], "description": row[2] if row[2] else ""}
                _CACHE["sessions"][ref] = session_info
                return session_info

        # 2. MATCH FALLBACK : Trouver la session par defaut (SessionDefault = 1)
        if _CACHE["default_session"]:
            return _CACHE["default_session"]

        query_default = """
            SELECT TOP 1 sp.SessionPositionID, sp.PositionReference, sp.Description
            FROM SessionPosition sp
            JOIN Session s ON sp.SessionID = s.SessionID
            WHERE s.SessionDefault = 1
        """
        cursor.execute(query_default)
        row = cursor.fetchone()
        if row:
            session_info = {"id": row[0], "reference": row[1], "description": row[2] if row[2] else "Description de poste non trouvee, session par defaut."}
            _CACHE["default_session"] = session_info
            return session_info

    except Exception as e:
        print(f"Error fetch session (read_db) : {e}")
    finally:
        if conn:
            conn.close()

    return {"id": fallback_id, "reference": fallback_ref, "description": fallback_desc}

async def fetch_session_by_reference(ref: str) -> dict:
    return await asyncio.to_thread(_sync_fetch_session_by_reference, ref)

def _sync_fetch_all_session_references() -> list:
    if _CACHE["session_references"] is not None:
        return _CACHE["session_references"]

    conn = get_db_connection()
    if not conn:
        return []
    
    references = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT PositionReference FROM SessionPosition WHERE PositionReference IS NOT NULL")
        for row in cursor.fetchall():
            references.append(row[0])
        _CACHE["session_references"] = references
    except Exception as e:
        print(f"Error fetching references: {e}")
    finally:
        if conn:
            conn.close()
            
    return references

async def fetch_all_session_references() -> list:
    return await asyncio.to_thread(_sync_fetch_all_session_references)

def _sync_fetch_all_institutions() -> list:
    if _CACHE["institutions"] is not None:
        return _CACHE["institutions"]

    conn = get_db_connection()
    if not conn:
        return []

    institutions = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT InstitutionID, InstitutionLabel FROM Institution")
        for row in cursor.fetchall():
            institutions.append({"InstitutionID": row[0], "Name": row[1]})
        _CACHE["institutions"] = institutions
    except Exception as e:
        print(f"Error fetching Institutions: {e}. Falling back to mock data.")
        institutions = [{"InstitutionID": 1, "Name": "Universite de Paris"}, {"InstitutionID": 2, "Name": "EPFL"}, {"InstitutionID": 3, "Name": "MIT"}]
        _CACHE["institutions"] = institutions
    finally:
        if conn:
            conn.close()

    return institutions

async def fetch_all_institutions() -> list:
    return await asyncio.to_thread(_sync_fetch_all_institutions)

def _sync_fetch_all_study_levels() -> list:
    if _CACHE["study_levels"] is not None:
        return _CACHE["study_levels"]

    conn = get_db_connection()
    if not conn:
        return []

    study_levels = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT StudyLevelID, StudyLevelLabel FROM StudyLevel")
        for row in cursor.fetchall():
            study_levels.append({"StudyLevelID": row[0], "Name": row[1]})
        _CACHE["study_levels"] = study_levels
    except Exception as e:
        print(f"Error fetching StudyLevels: {e}. Falling back to mock data.")
        study_levels = [{"StudyLevelID": 1, "Name": "Bac+2"}, {"StudyLevelID": 2, "Name": "Bac+3 (Licence)"}, {"StudyLevelID": 3, "Name": "Bac+5 (Master/Ingenieur)"}]
        _CACHE["study_levels"] = study_levels
    finally:
        if conn:
            conn.close()

    return study_levels

async def fetch_all_study_levels() -> list:
    return await asyncio.to_thread(_sync_fetch_all_study_levels)
