"""
Tests unitaires des helpers de cache et de la résolution de session (read_db.py).
On ne touche pas à la vraie base : _query_session_by_ref est testée avec un
faux curseur, et le cache TTL avec des manipulations directes du dictionnaire.
"""
import time
import types

from ai_service.ingestion import read_db
from ai_service.ingestion.read_db import (
    _cache_valid,
    _cache_store,
    _query_session_by_ref,
)


# ── Cache TTL : _cache_store / _cache_valid ─────────────────────────────────
def test_cache_store_then_valid():
    _cache_store("institutions", [{"InstitutionID": 1, "Name": "ENICAR"}])
    assert _cache_valid("institutions") is True
    assert read_db._CACHE["institutions"][0]["Name"] == "ENICAR"

def test_cache_invalid_when_never_stored():
    # une clé jamais enregistrée n'est pas valide
    read_db._CACHE_TIMESTAMPS.pop("study_levels", None)
    assert _cache_valid("study_levels") is False

def test_cache_expires_after_ttl(monkeypatch):
    _cache_store("session_references", ["REF-1"])
    # On simule un horodatage très ancien → dépasse le TTL
    read_db._CACHE_TIMESTAMPS["session_references"] = time.time() - 999999
    assert _cache_valid("session_references") is False


# ── _query_session_by_ref : avec un faux curseur (pas de vraie DB) ──────────
class _FakeCursor:
    """Curseur factice qui renvoie une ligne prédéfinie."""
    def __init__(self, row):
        self._row = row
    def execute(self, *args, **kwargs):
        pass
    def fetchone(self):
        return self._row

def test_query_session_found():
    cursor = _FakeCursor((42, "DEV-PY-01", "Développeur Python"))
    res = _query_session_by_ref(cursor, "DEV-PY-01")
    assert res == {"id": 42, "reference": "DEV-PY-01", "description": "Développeur Python"}

def test_query_session_not_found():
    cursor = _FakeCursor(None)
    assert _query_session_by_ref(cursor, "INCONNU") is None

def test_query_session_empty_ref_returns_none():
    cursor = _FakeCursor((1, "X", "Y"))
    assert _query_session_by_ref(cursor, "") is None
    assert _query_session_by_ref(cursor, "   ") is None
