"""
Test du helper de mise à jour du statut metadata (main.py).
Utilise un fichier temporaire — aucune dépendance externe.
"""
import json

from ai_service.main import _mark_metadata_done


def test_mark_metadata_done(tmp_path):
    # Prépare un metadata.json au statut 'pending'
    meta_file = tmp_path / "metadata.json"
    meta_file.write_text(json.dumps({"id": "5551", "status": "pending"}), encoding="utf-8")

    _mark_metadata_done(str(meta_file))

    # Le statut doit être passé à 'done', le reste préservé
    updated = json.loads(meta_file.read_text(encoding="utf-8"))
    assert updated["status"] == "done"
    assert updated["id"] == "5551"
