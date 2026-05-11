import pytest
import asyncio
from ai_service.processing.cleaner import clean_text

# Exemple de test d'intégration basique vérifiant que les modules de base fonctionnent ensemble
@pytest.mark.asyncio
async def test_text_cleaning_integration():
    raw_cv = "Candidat: Jean Dupont\nEmail: jean@test.com\nExpérience: 3 ans en Python."
    # On pourrait ici chainer avec l'extracteur de texte si on disposait d'un PDF,
    # puis vérifier que le nettoyeur formatte bien les données brutes.
    cleaned = clean_text(raw_cv)
    assert "jean@test.com" in cleaned
    assert "jean dupont" in cleaned.lower()

# Ajoutez ici vos prochains tests d'intégration, par ex:
# - Connexion à une base de données de test et exécution de requêtes (read_db / updater)
# - Appel HTTP vers le LLM (en mockant la réponse exacte) pour vérifier la désérialisation
# - Tester le flux complet de process_app_pipeline sur un fichier mock json.
