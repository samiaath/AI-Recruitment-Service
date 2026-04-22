import re
import unicodedata

def clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = unicodedata.normalize("NFKC", raw_text)
    text = re.sub(r'[^a-zA-Z0-9\s@\.+-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).lower().strip()
    return text
