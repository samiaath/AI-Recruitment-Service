from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    db_host: str = os.getenv("DB_HOST", r"DESKTOP-K3I5MGD\SQLEXPRESS")
    db_name: str = os.getenv("DB_NAME", "IID2_IIDRUT")
    db_driver: str = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

    imap_host: str = os.getenv("IMAP_HOST", "")
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")
    imap_folder: str = os.getenv("IMAP_FOLDER", "INBOX")

    ms_tenant_id: str = os.getenv("MS_TENANT_ID", "")
    ms_client_id: str = os.getenv("MS_CLIENT_ID", "")
    ms_client_secret: str = os.getenv("MS_CLIENT_SECRET", "")
    ms_user_id: str = os.getenv("MS_USER_ID", "")

    spacy_model: str = os.getenv("SPACY_MODEL", "fr_core_news_sm")
    ocr_lang: str = os.getenv("OCR_LANG", "fra")
    cv_directory: str = os.getenv("CV_DIRECTORY", "CVs")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
