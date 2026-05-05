import pytest
from ai_service.processing.cleaner import clean_text

def test_clean_text_basic():
    raw = "Hello   World!!! This is a TEST."
    cleaned = clean_text(raw)
    # Les '!' ne sont pas dans la liste des caractères conservés par défaut, ils doivent disparaître
    assert cleaned == "Hello World This is a TEST."

def test_clean_text_special_tech_chars():
    raw = "I am a C# and C++ developer. I work with CI/CD and R&D."
    cleaned = clean_text(raw)
    assert "C#" in cleaned
    assert "CI/CD" in cleaned
    assert "R&D" in cleaned

def test_clean_text_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""

def test_clean_text_accents():
    raw = "C'est un résumé avec des accents éàè."
    cleaned = clean_text(raw)
    # L'apostrophe disparaît car pas dans la regex, les accents sont soit normalisés soit conservés si intégrés post-NFKC
    # C'est un test simple pour voir si ça ne crashe pas.
    assert isinstance(cleaned, str)
    assert len(cleaned) > 0
