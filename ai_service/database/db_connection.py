import pyodbc
from contextlib import contextmanager
import time

DB_DRIVER = "{ODBC Driver 17 for SQL Server}"
DB_SERVER = r"DESKTOP-K3I5MGD\SQLEXPRESS"
DB_DATABASE = "IID2_IIDRUT"

@contextmanager
def get_db_connection():
    """Context manager with automatic retry + cleanup"""
    max_retries = 3
    conn_str = f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_DATABASE};Trusted_Connection=yes"
    
    conn = None
    
    # 1. Établir la connexion avec un système de réessai
    for attempt in range(max_retries):
        try:
            conn = pyodbc.connect(conn_str, timeout=30)
            break  # Connexion réussie, on sort de la boucle de retry
        except pyodbc.Error as e:
            if attempt == max_retries - 1:
                print(f"DB Error (make sure your SQL DB is running/configured): {e}")
                raise e
            time.sleep(2 ** attempt)  # Exponential backoff

    # 2. Fournir la connexion au bloc `with` et garantir sa fermeture
    try:
        yield conn
        conn.commit()  # Auto-commit si tout s'est bien passé dans le bloc `with`
    except Exception as e:
        conn.rollback()  # Annuler les changements si une erreur survient
        print(f"[DB] Erreur SQL attrapée : {e}")
        raise  # On relève l'erreur pour la voir dans les logs
    finally:
        if conn:
            try:
                conn.close()
            except pyodbc.Error:
                pass