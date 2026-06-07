"""
Tests unitaires des fonctions pures du scoring (scorer.py).
Aucune dépendance externe : on teste les helpers déterministes et le chemin
de sortie anticipée de compute_score (description vide → pas d'appel Mistral).
"""
import asyncio
import types

from ai_service.ai.scorer import (
    _score_level,
    _build_result,
    _generate_fallback_summary,
    _generate_fallback_strengths,
    _generate_fallback_weaknesses,
    compute_score,
)
from ai_service.models import ScoreBreakdown


# ── _score_level : tranche textuelle selon le score ─────────────────────────
def test_score_level_excellent():
    assert _score_level(85) == "Excellent"

def test_score_level_bon():
    assert _score_level(70) == "Bon"

def test_score_level_moyen():
    assert _score_level(50) == "Moyen"

def test_score_level_faible():
    assert _score_level(20) == "Faible"


# ── _generate_fallback_summary : message selon la moyenne ───────────────────
def test_fallback_summary_high():
    assert "parfaitement" in _generate_fallback_summary(90, 90, 90, 90)

def test_fallback_summary_low():
    assert _generate_fallback_summary(10, 10, 10, 10).startswith("Profil ne correspondant")


# ── _build_result : structure du résultat ───────────────────────────────────
def test_build_result_structure():
    bd = ScoreBreakdown(skills_match=80, experience_years=70, education_level=90, seniority_match=60)
    res = _build_result(75.0, bd, 1.0, "Bon profil", "Points forts X", "Points faibles Y")
    assert res["score"] == 75.0
    assert res["level"] == "Bon"
    assert "breakdown" in res
    assert "Points forts" in res["summary"]
    assert "Points faibles" in res["summary"]


# ── _generate_fallback_strengths / weaknesses : avec un faux candidat ───────
def _fake_candidate():
    """Objet minimal imitant ExtractedApplicationData pour les fallbacks."""
    skill = types.SimpleNamespace(SkillDescription="Python")
    degree = types.SimpleNamespace(DegreeLabel="Master Informatique")
    return types.SimpleNamespace(
        skills=[skill],
        degrees=[degree],
        experiences=[],
        total_years_experience=0.5,
        professional_years_only=0.0,
    )

def test_fallback_strengths_returns_text():
    out = _generate_fallback_strengths(_fake_candidate(), "offre", s_skills=80, s_edu=80)
    assert isinstance(out, str) and len(out) > 0

def test_fallback_weaknesses_returns_text():
    out = _generate_fallback_weaknesses(_fake_candidate(), "offre", s_exp=20, s_sen=20)
    assert isinstance(out, str) and len(out) > 0


# ── compute_score : sortie anticipée si description vide (pas d'appel LLM) ───
def test_compute_score_empty_description():
    result = asyncio.run(compute_score(None, ""))
    assert result["score"] == 50.0
    assert result["level"] == "Moyen"
    assert "summary" in result
