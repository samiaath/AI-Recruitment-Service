import pyodbc

DB_DRIVER = "{ODBC Driver 17 for SQL Server}"
DB_SERVER = r"DESKTOP-K3I5MGD\SQLEXPRESS"
DB_DATABASE = "IID2_IIDRUT"

def get_db_connection():
    try:
        conn_str = f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_DATABASE};Trusted_Connection=yes"
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"DB Error (make sure your SQL DB is runnning/configured): {e}")
        return None
