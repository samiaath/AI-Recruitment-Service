import re
import unicodedata

def clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = unicodedata.normalize("NFKC", raw_text)
    # On ajoute # (pour C#), / (pour CI/CD), & (R&D) et on garde le reste
    text = re.sub(r'[^a-zA-Z0-9\s@\.+#/&-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).lower().strip()
    return text
