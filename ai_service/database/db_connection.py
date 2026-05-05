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
    for attempt in range(max_retries):
        try:
            conn = pyodbc.connect(conn_str, timeout=30)
            yield conn
            conn.commit()  # Auto-commit on success
            return
        except pyodbc.Error as e:
            if attempt == max_retries - 1:
                print(f"DB Error (make sure your SQL DB is runnning/configured): {e}")
                raise e
            time.sleep(2 ** attempt)  # Exponential backoff
        finally:
            if conn:
                try:
                    conn.close()
                except pyodbc.Error:
                    pass
