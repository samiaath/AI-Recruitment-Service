import pyodbc
from contextlib import contextmanager
import time
from ..config import settings

# Paramètres de connexion lus depuis la config centrale (config.py / variables
# d'environnement). Les valeurs par défaut y sont identiques à l'ancien codage en
# dur, donc le comportement ne change pas — mais on peut désormais surcharger
# l'hôte/la base via un fichier .env sans toucher au code.
DB_DRIVER = "{" + settings.db_driver + "}"   # pyodbc attend le driver entre accolades
DB_SERVER = settings.db_host
DB_DATABASE = settings.db_name

@contextmanager
def get_db_connection():
    """
    Ouvre une connexion SQL Server (authentification Windows) en gérant :
    - jusqu'à 3 tentatives avec backoff exponentiel si la base est momentanément indisponible ;
    - le commit automatique en sortie de bloc, ou le rollback en cas d'erreur ;
    - la fermeture garantie de la connexion.

    S'utilise avec `with get_db_connection() as conn:`.
    """
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