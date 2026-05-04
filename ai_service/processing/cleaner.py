import re
import unicodedata

_NOISE_PATTERNS = [
    r"page\s+\d+\s*(sur|of|\/)\s*\d+",
    r"curriculum\s+vitae",
    r"confidentiel",
]

def clean_text(raw_text: str, preserve_structure: bool = True) -> str:
    """
    Nettoie le texte brut extrait d'un CV.

    preserve_structure=True (défaut) :
        Conserve les retours à la ligne comme séparateurs sémantiques.
        CRUCIAL pour que Mistral distingue les sections et identifie
        correctement "Expériences professionnelles" vs "Projets scolaires".

    preserve_structure=False :
        Aplatit en une ligne (usage legacy).
    """
    if not raw_text:
        return ""

    text = unicodedata.normalize("NFKC", raw_text)

    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # Conserve : lettres, chiffres, @, ., +, #, /, &, -, (, ), :, virgule, apostrophe, newline
    text = re.sub(r"[^a-zA-ZÀ-ÿ0-9\s@\.+#/&\-\(\):,\'\"\n]", " ", text)

    # Réduction espaces horizontaux (sans toucher aux \n)
    text = re.sub(r"[ \t]+", " ", text)

    if preserve_structure:
        # Max 2 sauts de ligne consécutifs (préserve séparation des sections)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
    else:
        text = re.sub(r"\s+", " ", text)

    return text.strip()
