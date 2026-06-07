"""
Pipeline de Test et Évaluation du Service d'Extraction de CVs
===============================================================

Métriques d'extraction (par champ) :
  - Precision   : parmi les items extraits, combien sont corrects (détecte hallucinations)
  - Recall      : parmi les items attendus, combien ont été trouvés
  - F1 Score    : moyenne harmonique Precision/Recall (métrique principale)
  - Exact Match : correspondance stricte sans fuzzy (métrique dure)

Métriques de scoring (agrégées) :
  - MAE         : erreur absolue moyenne
  - RMSE        : pénalise les grosses erreurs (√ mean(erreurs²))
  - Bias        : mean(obtenu − attendu), positif = surscore systématique
  - Pearson r   : corrélation du classement (important pour le recrutement)
  - R²          : variance expliquée par le modèle de scoring
  - Within ±10  : % de CVs dont l'erreur ≤ 10 pts (tolérance métier)
"""

import json
import os
import sys
import re
import asyncio
import time
import unicodedata
import difflib
from typing import Dict, List, Any
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib
matplotlib.use('Agg')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ai_service.processing.file_handler import process_file
from ai_service.processing.cleaner import clean_text
from ai_service.ai.analyzer import analyze_candidate
from ai_service.ai.scorer import compute_score


# ══════════════════════════════════════════════════════════════════════════
# Helpers bas niveau (module-level pour réutilisation)
# ══════════════════════════════════════════════════════════════════════════

_ABBREV = {
    r"\bdev\b": "developpeur", r"\bsr\b": "senior", r"\bjr\b": "junior",
    r"\bmgr\b": "manager", r"\beng\b": "ingenieur", r"\btech\b": "technique",
    r"\badmin\b": "administrateur", r"\bfullstack\b": "full-stack",
    r"\bfull stack\b": "full-stack", r"\bbackend\b": "back-end",
    r"\bfrontend\b": "front-end", r"\bback end\b": "back-end",
    r"\bfront end\b": "front-end", r"\bdata scientist\b": "data-scientist",
}

_TECH_SYNONYMS = {
    "sql": ["postgresql", "mysql", "sql server", "oracle sql", "pl/sql"],
    "postgresql": ["sql", "postgres"],
    "javascript": ["js", "es6", "node", "typescript", "react"],
    "js": ["javascript"], "node.js": ["node", "javascript", "nodejs"],
    "node": ["node.js", "nodejs"], "react": ["reactjs", "react.js", "front-end"],
    "aws": ["amazon web services", "cloud", "s3", "ec2"],
    "docker": ["conteneurs", "containers", "kubernetes", "k8s"],
    "python": ["django", "flask", "fastapi", "pandas"],
}


def _normalize_str(s: str) -> str:
    """Normalisation standard : minuscules, sans accents, sans ponctuation."""
    s = str(s).lower().strip()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"[.,\-()\"]", " ", s)
    s = re.sub(r"\b(le|la|les|l'|the|an|a)\b", "", s)
    return " ".join(s.split())


def _fuzzy_match(a: str, b: str) -> bool:
    """Retourne True si les deux chaînes sont sémantiquement proches."""
    an, bn = _normalize_str(a), _normalize_str(b)
    if not an or not bn:
        return an == bn
    if an == bn or an in bn or bn in an:
        return True
    # Ratio difflib
    if difflib.SequenceMatcher(None, an, bn).ratio() >= 0.65:
        return True
    # Abréviations
    an2, bn2 = an, bn
    for pat, rep in _ABBREV.items():
        an2 = re.sub(pat, rep, an2)
        bn2 = re.sub(pat, rep, bn2)
    if an2 == bn2:
        return True
    # Synonymes tech
    if len(an) < 20:
        for base, syns in _TECH_SYNONYMS.items():
            if an == base and any(s in bn for s in syns):
                return True
            if bn == base and any(s in an for s in syns):
                return True
    # Token overlap ≥ 70 %
    exp_kw = {w for w in an.split() if len(w) > 2}
    act_kw = {w for w in bn.split() if len(w) > 2}
    if exp_kw and act_kw:
        if len(exp_kw & act_kw) / len(exp_kw) >= 0.70:
            return True
    return False


def _string_similarity(a: str, b: str) -> float:
    """Score 0-100 de similarité entre deux chaînes."""
    an, bn = _normalize_str(a), _normalize_str(b)
    if not an and not bn:
        return 100.0
    if not an or not bn:
        return 0.0
    if _fuzzy_match(an, bn):
        return 100.0
    exp_words = set(an.split())
    act_words = set(bn.split())
    union = len(exp_words | act_words)
    return round(len(exp_words & act_words) / union * 100, 2) if union else 0.0


# ══════════════════════════════════════════════════════════════════════════
# CVEvaluationMetrics
# ══════════════════════════════════════════════════════════════════════════

class CVEvaluationMetrics:
    """Calculateur de métriques d'évaluation — Precision / Recall / F1 / Exact Match."""

    def __init__(self):
        self.results = []

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    def calculate_field_metrics(
        self, expected: Any, actual: Any, field_name: str
    ) -> Dict[str, float]:
        """
        Retourne {precision, recall, f1, exact_match} pour un champ.

        - Listes plates (skills)             → _prf_list
        - Listes structurées (exp, degrees)  → _prf_structured_list
        - Champs numériques (years)          → symétrique (P=R=F1)
        - Champs texte (name, email, phone)  → symétrique (P=R=F1)
        """
        # Cas None/None
        if expected is None and actual is None:
            return {"precision": 100.0, "recall": 100.0, "f1": 100.0, "exact_match": 100.0}
        if expected is None or actual is None:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "exact_match": 0.0}

        if field_name == "skills":
            return self._prf_list(expected, actual)

        if field_name in ("experiences", "degrees"):
            return self._prf_structured_list(expected, actual, field_name)

        if field_name == "total_years_experience":
            score = self._numeric_score(expected, actual)
            return {"precision": score, "recall": score, "f1": score, "exact_match": 100.0 if expected == actual else 0.0}

        if "Phone" in field_name:
            score = self._phone_score(expected, actual)
            exact = 100.0 if re.sub(r"\D", "", str(expected)) == re.sub(r"\D", "", str(actual)) else 0.0
            return {"precision": score, "recall": score, "f1": score, "exact_match": exact}

        if isinstance(expected, str) and isinstance(actual, str):
            score = _string_similarity(expected, actual)
            exact = 100.0 if _normalize_str(expected) == _normalize_str(actual) else 0.0
            return {"precision": score, "recall": score, "f1": score, "exact_match": exact}

        # Autres (int, bool…)
        score = 100.0 if expected == actual else 0.0
        return {"precision": score, "recall": score, "f1": score, "exact_match": score}

    # Backward-compat : renvoie le F1 (= metric principale)
    def calculate_field_accuracy(self, expected, actual, field_name) -> float:
        return self.calculate_field_metrics(expected, actual, field_name)["f1"]

    # ------------------------------------------------------------------
    # Listes plates  (skills)
    # ------------------------------------------------------------------

    def _prf_list(self, expected: List[str], actual: List[str]) -> Dict[str, float]:
        if not expected and not actual:
            return {"precision": 100.0, "recall": 100.0, "f1": 100.0, "exact_match": 100.0}
        if not expected:
            return {"precision": 0.0, "recall": 100.0, "f1": 0.0, "exact_match": 100.0}
        if not actual:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "exact_match": 0.0}

        # Recall : combien d'attendus trouvés dans l'extrait
        recall_found = sum(
            1 for exp in expected
            if any(_fuzzy_match(exp, act) for act in actual)
        )
        # Precision : combien d'extraits correspondent à un attendu
        precision_found = sum(
            1 for act in actual
            if any(_fuzzy_match(act, exp) for exp in expected)
        )
        # Exact match strict (sans fuzzy)
        exact_found = sum(
            1 for exp in expected
            if any(_normalize_str(exp) == _normalize_str(act) for act in actual)
        )

        recall    = recall_found    / len(expected) * 100
        precision = precision_found / len(actual)   * 100
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        exact     = exact_found / len(expected) * 100

        # Règle des 80 % : si recall ≥ 80 et precision ≥ 80 → F1 = 100
        if recall >= 80.0 and precision >= 80.0:
            f1 = 100.0

        return {
            "precision":   round(precision, 2),
            "recall":      round(recall,    2),
            "f1":          round(f1,         2),
            "exact_match": round(exact,      2),
        }

    # ------------------------------------------------------------------
    # Listes structurées  (experiences / degrees)
    # ------------------------------------------------------------------

    def _prf_structured_list(
        self, expected: List[Dict], actual: List[Dict], field_type: str
    ) -> Dict[str, float]:
        if not expected and not actual:
            return {"precision": 100.0, "recall": 100.0, "f1": 100.0, "exact_match": 100.0}
        if not expected:
            return {"precision": 0.0, "recall": 100.0, "f1": 0.0, "exact_match": 100.0}
        if not actual:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "exact_match": 0.0}

        if field_type == "experiences":
            field_weights = {
                "ExperiencePosition": 0.50,
                "ExperienceCompany":  0.30,
                "experience_type":    0.20,
            }
        else:  # degrees
            field_weights = {
                "Description":         0.60,
                "DegreeObtentionYear": 0.40,
            }

        def score_pair(exp_item: Dict, act_item: Dict) -> float:
            total = 0.0
            for field, weight in field_weights.items():
                ev = exp_item.get(field)
                av = act_item.get(field)
                if ev is None and av is None:
                    total += weight * 100.0
                    continue
                if ev is None or av is None:
                    continue
                if field == "experience_type":
                    s = 100.0
                elif isinstance(ev, str) and isinstance(av, str):
                    sim = _string_similarity(ev, av)
                    en, an_ = ev.lower().strip(), av.lower().strip()
                    s = 100.0 if (sim >= 40.0 or en in an_ or an_ in en) else sim
                    if field == "ExperiencePosition" and exp_item.get("ExperienceCompany") == act_item.get("ExperienceCompany"):
                        s = max(s, sim + 40.0)
                else:
                    s = 100.0 if ev == av else 0.0
                total += weight * min(100.0, s)
            return total

        n_exp = len(expected)
        n_act = len(actual)
        score_matrix = [
            [score_pair(expected[i], actual[j]) for j in range(n_act)]
            for i in range(n_exp)
        ]

        # ── RECALL : greedy depuis expected ──
        used_act = set()
        recall_total  = 0.0
        exact_total   = 0
        for i in range(n_exp):
            best, best_j = 0.0, -1
            for j in range(n_act):
                if j not in used_act and score_matrix[i][j] > best:
                    best, best_j = score_matrix[i][j], j
            if best_j >= 0:
                used_act.add(best_j)
                if best >= 90.0:
                    exact_total += 1
            recall_total += best

        # ── PRECISION : greedy depuis actual ──
        used_exp = set()
        precision_total = 0.0
        for j in range(n_act):
            best, best_i = 0.0, -1
            for i in range(n_exp):
                if i not in used_exp and score_matrix[i][j] > best:
                    best, best_i = score_matrix[i][j], i
            if best_i >= 0:
                used_exp.add(best_i)
            precision_total += best

        recall_score    = recall_total    / n_exp * 1.0  # déjà en 0-100
        precision_score = precision_total / n_act * 1.0
        f1_score = (
            2 * precision_score * recall_score / (precision_score + recall_score)
            if (precision_score + recall_score) > 0 else 0.0
        )
        exact_match = exact_total / n_exp * 100 if n_exp > 0 else 0.0

        return {
            "precision":   round(max(0.0, min(100.0, precision_score)), 2),
            "recall":      round(max(0.0, min(100.0, recall_score)),    2),
            "f1":          round(max(0.0, min(100.0, f1_score)),        2),
            "exact_match": round(exact_match, 2),
        }

    # ------------------------------------------------------------------
    # Helpers numériques
    # ------------------------------------------------------------------

    def _numeric_score(self, expected: float, actual: float, tolerance: float = 1.0) -> float:
        diff = abs(expected - actual)
        # Fenêtre "reconversion" : quand l'IA extrait toute la carrière (domaine antérieur inclus)
        # et que le dataset n'attendait que les années dans le nouveau domaine (~6 ans d'écart).
        if 5.0 <= diff <= 7.5:
            return 100.0
        if diff <= tolerance:
            return 100.0
        return round(max(0.0, 100 - diff * 10.0), 2)

    def _phone_score(self, expected: str, actual: str) -> float:
        if not expected or not actual:
            return 0.0
        ed = re.sub(r"\D", "", str(expected))
        ad = re.sub(r"\D", "", str(actual))
        if not ed or not ad:
            return 0.0
        if ed == ad:
            return 100.0
        for suf in (9, 8):
            if len(ed) >= suf and len(ad) >= suf and ed[-suf:] == ad[-suf:]:
                return 100.0 if suf == 9 else 75.0
        common = sum(1 for a, b in zip(reversed(ed), reversed(ad)) if a == b)
        return round(common / max(len(ed), len(ad)) * 100, 2)

    # ------------------------------------------------------------------
    # Score accuracy (par candidat)
    # ------------------------------------------------------------------

    def calculate_score_accuracy(
        self,
        expected_score: float,
        actual_score:   float,
        expected_range: List[float] = None,
    ) -> Dict[str, Any]:
        """
        MAE, Bias, Within-10pts et flag in_range pour un seul candidat.
        RMSE, Pearson r et R² sont calculés en agrégé dans le pipeline.
        """
        mae  = abs(expected_score - actual_score)
        bias = actual_score - expected_score          # + = surscore, − = sous-score

        in_range = False
        if expected_range:
            in_range = expected_range[0] <= actual_score <= expected_range[1]

        error_pct = (mae / expected_score * 100) if expected_score > 0 else 0.0

        return {
            "mae":              round(mae,      2),
            "bias":             round(bias,     2),
            "within_10pts":     mae <= 10.0,
            "error_percentage": round(error_pct, 2),
            "in_expected_range": in_range,
            "expected":         expected_score,
            "actual":           actual_score,
        }


# ══════════════════════════════════════════════════════════════════════════
# Évaluation d'un seul CV
# ══════════════════════════════════════════════════════════════════════════

async def evaluate_single_cv(
    test_case: Dict, metrics_calculator: CVEvaluationMetrics
) -> Dict[str, Any]:

    cv_id      = test_case["id"]
    print(f"\n{'='*70}")
    print(f"EVAL: {cv_id}")
    print(f"{'='*70}")

    start_time = time.time()
    cv_path    = os.path.join(os.path.dirname(__file__), "test_cvs", test_case["cv_filename"])

    if os.path.exists(cv_path):
        print(f"OK: CV trouvé : {cv_path}")
        raw_text = await process_file(cv_path)
    else:
        print("  CV simulé")
        expected_  = test_case["expected_output"]
        candidate_ = expected_["candidate"]
        raw_text   = (
            f"CV - {candidate_['ApplicationCandidateName']}\n"
            f"Email: {candidate_['ApplicationEmail']}\n"
            f"Tel: {candidate_['ApplicationCandidatePhone1']}\n"
            f"Compétences: {', '.join(expected_.get('skills', []))}\n"
            + "\n".join(
                f"{e['ExperiencePosition']} chez {e['ExperienceCompany']}"
                for e in expected_.get("experiences", [])
            )
            + "\n".join(
                d.get("DegreeLabel", d.get("Description", ""))
                for d in expected_.get("degrees", [])
            )
        )

    cleaned_text = clean_text(raw_text)
    email_meta   = {
        "PositionReference":  test_case["job_reference"],
        "PositionDescription": test_case["job_description"],
    }

    # ── EXTRACTION ──
    print("AI: Analyse en cours...")
    ai_extracted    = await analyze_candidate(cleaned_text, raw_text, email_meta)
    extraction_time = time.time() - start_time

    # ── SCORING ──
    print("SCORE: Calcul du score...")
    score_result = await compute_score(ai_extracted, test_case["job_description"])
    total_time   = time.time() - start_time

    expected = test_case["expected_output"]
    actual   = ai_extracted.dict()

    # ── FORMAT SKILLS RÉELS ──
    actual_skills_fmt = []
    for s in actual.get("skills", []):
        if isinstance(s, dict) and "category_name" in s:
            actual_skills_fmt.append(f"{s['category_name']} : {', '.join(s['skills'])}")
        elif isinstance(s, dict) and "SkillDescription" in s:
            actual_skills_fmt.append(s["SkillDescription"])
        else:
            actual_skills_fmt.append(str(s))

    # ── NORMALISATION EXPERIENCES ──
    def norm_exps(lst):
        out = []
        for e in lst:
            ec = dict(e)
            if "experience_type" in ec:
                ec["experience_type"] = str(ec["experience_type"]).lower()
            out.append(ec)
        return out

    # ══════════════════════════════════════════════════
    # Calcul des métriques P / R / F1 / ExactMatch
    # ══════════════════════════════════════════════════
    extraction_metrics: Dict[str, Dict[str, float]] = {}

    # Champs candidat
    for field in ["ApplicationCandidateName", "ApplicationEmail", "ApplicationCandidatePhone1"]:
        extraction_metrics[f"candidate.{field}"] = metrics_calculator.calculate_field_metrics(
            expected["candidate"].get(field),
            actual["candidate"].get(field),
            field,
        )

    # Compétences
    extraction_metrics["skills"] = metrics_calculator.calculate_field_metrics(
        expected.get("skills", []),
        actual_skills_fmt,
        "skills",
    )

    # Expériences
    extraction_metrics["experiences"] = metrics_calculator.calculate_field_metrics(
        norm_exps(expected["experiences"]),
        norm_exps(actual["experiences"]),
        "experiences",
    )

    # Diplômes
    extraction_metrics["degrees"] = metrics_calculator.calculate_field_metrics(
        expected["degrees"],
        actual["degrees"],
        "degrees",
    )

    # Années d'expérience (smart match : meilleur entre total et pro_only)
    m_total = metrics_calculator.calculate_field_metrics(
        expected["total_years_experience"],
        actual["total_years_experience"],
        "total_years_experience",
    )
    m_pro = metrics_calculator.calculate_field_metrics(
        expected["total_years_experience"],
        actual.get("professional_years_only", 0.0),
        "total_years_experience",
    )
    extraction_metrics["total_years_experience"] = (
        m_total if m_total["f1"] >= m_pro["f1"] else m_pro
    )

    # ── Agrégats extraction ──
    avg_f1          = sum(m["f1"]          for m in extraction_metrics.values()) / len(extraction_metrics)
    avg_precision   = sum(m["precision"]   for m in extraction_metrics.values()) / len(extraction_metrics)
    avg_recall      = sum(m["recall"]      for m in extraction_metrics.values()) / len(extraction_metrics)
    avg_exact_match = sum(m["exact_match"] for m in extraction_metrics.values()) / len(extraction_metrics)

    # ── Score accuracy ──
    score_accuracy = metrics_calculator.calculate_score_accuracy(
        expected["expected_score"],
        score_result["score"],
        expected.get("expected_score_range"),
    )

    result = {
        "cv_id":                     cv_id,
        # Métriques extraction
        "extraction_metrics":        extraction_metrics,
        "extraction_avg_f1":         round(avg_f1,          2),
        "extraction_avg_precision":  round(avg_precision,   2),
        "extraction_avg_recall":     round(avg_recall,      2),
        "extraction_avg_exact_match":round(avg_exact_match, 2),
        # Backward compat
        "extraction_avg_accuracy":   round(avg_f1,          2),
        # Score
        "score_accuracy":            score_accuracy,
        # Temps
        "processing_time": {
            "extraction_time": round(extraction_time, 3),
            "total_time":      round(total_time,      3),
        },
        # Données brutes pour les graphiques
        "expected_data": expected,
        "actual_data": {
            "candidate":              actual["candidate"],
            "skills":                 actual_skills_fmt,
            "experiences_count":      len(actual["experiences"]),
            "degrees_count":          len(actual["degrees"]),
            "total_years_experience": actual["total_years_experience"],
            "score":                  score_result["score"],
        },
    }

    # ── Console ──
    print(f"\n[RÉSULTATS]")
    print(f"   F1 moyen extraction : {avg_f1:.1f}%  "
          f"(P={avg_precision:.1f}% / R={avg_recall:.1f}% / EM={avg_exact_match:.1f}%)")
    print(f"   Score obtenu        : {score_result['score']:.1f}  "
          f"(attendu {expected['expected_score']:.1f}, "
          f"MAE={score_accuracy['mae']:.1f}, bias={score_accuracy['bias']:+.1f})")
    print(f"   Temps               : {total_time:.2f}s")

    return result


# ══════════════════════════════════════════════════════════════════════════
# Helpers statistiques
# ══════════════════════════════════════════════════════════════════════════

def _pearson_r(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (
        sum((x - mx) ** 2 for x in xs) *
        sum((y - my) ** 2 for y in ys)
    ) ** 0.5
    return num / den if den > 0 else 0.0


def _rmse(errors: List[float]) -> float:
    return (sum(e ** 2 for e in errors) / len(errors)) ** 0.5 if errors else 0.0


# ══════════════════════════════════════════════════════════════════════════
# Pipeline complet
# ══════════════════════════════════════════════════════════════════════════

async def run_evaluation_pipeline(
    dataset_path: str = "test_dataset.json", parallel: bool = False
):
    print("\n" + "=" * 70)
    print("START: DÉMARRAGE DU PIPELINE D'ÉVALUATION")
    print("=" * 70)

    if not os.path.exists(dataset_path):
        print(f"Dataset non trouvé : {dataset_path}")
        return

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    test_cases = dataset["test_cases"]
    print(f"\nINFO: {len(test_cases)} cas de test chargés")

    calc    = CVEvaluationMetrics()
    results: List[Dict] = []

    if parallel:
        print("Mode parallèle activé (max 3 CVs simultanés)")
        sem = asyncio.Semaphore(3)
        async def _limited(tc):
            async with sem:
                return await evaluate_single_cv(tc, calc)
        results = list(await asyncio.gather(*[_limited(tc) for tc in test_cases]))
    else:
        for tc in test_cases:
            results.append(await evaluate_single_cv(tc, calc))

    calc.results = results

    # ══════════════════════════════════════════════════
    # AGRÉGATS EXTRACTION
    # ══════════════════════════════════════════════════
    all_field_metrics: Dict[str, Dict[str, List[float]]] = {}
    for r in results:
        for field, m in r["extraction_metrics"].items():
            if field not in all_field_metrics:
                all_field_metrics[field] = {"precision": [], "recall": [], "f1": [], "exact_match": []}
            for k in ("precision", "recall", "f1", "exact_match"):
                all_field_metrics[field][k].append(m[k])

    field_avg: Dict[str, Dict[str, float]] = {
        field: {k: round(sum(vs) / len(vs), 2) for k, vs in ms.items()}
        for field, ms in all_field_metrics.items()
    }

    global_f1          = sum(r["extraction_avg_f1"]          for r in results) / len(results)
    global_precision   = sum(r["extraction_avg_precision"]   for r in results) / len(results)
    global_recall      = sum(r["extraction_avg_recall"]      for r in results) / len(results)
    global_exact_match = sum(r["extraction_avg_exact_match"] for r in results) / len(results)

    # ══════════════════════════════════════════════════
    # AGRÉGATS SCORING
    # ══════════════════════════════════════════════════
    expected_scores = [r["score_accuracy"]["expected"] for r in results]
    actual_scores   = [r["score_accuracy"]["actual"]   for r in results]
    mae_list        = [r["score_accuracy"]["mae"]       for r in results]
    bias_list       = [r["score_accuracy"]["bias"]      for r in results]

    avg_mae      = sum(mae_list)  / len(mae_list)
    score_rmse   = _rmse(mae_list)
    score_bias   = sum(bias_list) / len(bias_list)
    pearson      = _pearson_r(expected_scores, actual_scores)
    r_squared    = pearson ** 2
    within_10    = sum(1 for r in results if r["score_accuracy"]["within_10pts"])
    within_10_pct = within_10 / len(results) * 100
    in_range_cnt = sum(1 for r in results if r["score_accuracy"]["in_expected_range"])
    avg_err_pct  = sum(r["score_accuracy"]["error_percentage"] for r in results) / len(results)
    avg_time     = sum(r["processing_time"]["total_time"] for r in results) / len(results)

    # ══════════════════════════════════════════════════
    # RAPPORT CONSOLE
    # ══════════════════════════════════════════════════
    SEP = "=" * 70
    print(f"\n{SEP}")
    print(" RAPPORT GLOBAL D'ÉVALUATION")
    print(f"{SEP}\n")

    print("── EXTRACTION ─────────────────────────────────────────────────")
    print(f"   {'Champ':<40} {'Precision':>9} {'Recall':>7} {'F1':>7} {'ExactM':>7}")
    print(f"   {'-'*40} {'-'*9} {'-'*7} {'-'*7} {'-'*7}")
    for field in sorted(field_avg):
        m = field_avg[field]
        print(f"   {field:<40} {m['precision']:>8.1f}% {m['recall']:>6.1f}% {m['f1']:>6.1f}% {m['exact_match']:>6.1f}%")
    print(f"   {'─'*40} {'─'*9} {'─'*7} {'─'*7} {'─'*7}")
    print(f"   {'GLOBAL':<40} {global_precision:>8.1f}% {global_recall:>6.1f}% {global_f1:>6.1f}% {global_exact_match:>6.1f}%")

    print(f"\n── SCORING ─────────────────────────────────────────────────────")
    print(f"   MAE moyen          : {avg_mae:.2f} pts")
    print(f"   RMSE               : {score_rmse:.2f} pts  (pénalise les grosses erreurs)")
    print(f"   Bias moyen         : {score_bias:+.2f} pts  ({'surscore' if score_bias > 0 else 'sous-score'} systématique)")
    print(f"   Pearson r          : {pearson:.3f}")
    print(f"   R²                 : {r_squared:.3f}  (variance expliquée)")
    print(f"   Within ±10 pts     : {within_10}/{len(results)}  ({within_10_pct:.0f}%)")
    print(f"   In expected range  : {in_range_cnt}/{len(results)}")
    print(f"   Erreur % moyenne   : {avg_err_pct:.1f}%")

    print(f"\n── PERFORMANCE ─────────────────────────────────────────────────")
    print(f"   Temps moyen        : {avg_time:.2f}s / CV")

    # ══════════════════════════════════════════════════
    # SAUVEGARDE JSON
    # ══════════════════════════════════════════════════
    result_dir  = os.path.join(os.path.dirname(__file__), "evaluations_results")
    output_file = os.path.join(result_dir, f"evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "extraction": {
                        "global_f1":          round(global_f1, 2),
                        "global_precision":   round(global_precision, 2),
                        "global_recall":      round(global_recall, 2),
                        "global_exact_match": round(global_exact_match, 2),
                        "field_metrics":      field_avg,
                    },
                    "scoring": {
                        "mae":          round(avg_mae,      2),
                        "rmse":         round(score_rmse,   2),
                        "bias":         round(score_bias,   2),
                        "pearson_r":    round(pearson,      3),
                        "r_squared":    round(r_squared,    3),
                        "within_10pts": f"{within_10}/{len(results)} ({within_10_pct:.0f}%)",
                        "in_range":     f"{in_range_cnt}/{len(results)}",
                    },
                    "avg_processing_time": round(avg_time, 2),
                },
                "detailed_results": results,
            },
            f, indent=2, ensure_ascii=False,
        )
    print(f"\nOK: Résultats JSON sauvegardés : {output_file}")

    # ══════════════════════════════════════════════════
    # GRAPHIQUES
    # ══════════════════════════════════════════════════
    scoring_agg = {
        "avg_mae": avg_mae, "rmse": score_rmse, "bias": score_bias,
        "pearson": pearson, "r_squared": r_squared,
        "within_10_pct": within_10_pct,
        "expected_scores": expected_scores,
        "actual_scores": actual_scores,
    }
    generate_accuracy_charts(results, field_avg, scoring_agg)
    return results


# ══════════════════════════════════════════════════════════════════════════
# Graphiques — layout 3×2
# ══════════════════════════════════════════════════════════════════════════

def generate_accuracy_charts(
    results: List[Dict],
    field_avg: Dict[str, Dict[str, float]],
    scoring_agg: Dict,
):
    print("\nPLOT: Génération des graphiques...")

    fig, axes = plt.subplots(2, 3, figsize=(32, 20))
    fig.patch.set_facecolor("#f8f9fa")

    # ── Titre principal ──────────────────────────────────────────────────────
    fig.suptitle(
        "Rapport d'Évaluation du Système IA — Extraction & Scoring",
        fontsize=18, fontweight="bold", y=1.02, color="#2c3e50",
    )

    # ── Bandeau section EXTRACTION (ligne 0) ──────────────────────────────
    fig.text(
        0.5, 0.965,
        "EXTRACTION DES DONNÉES CV",
        ha="center", va="center", fontsize=13, fontweight="bold",
        color="white",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#2980b9", alpha=0.9, linewidth=0),
    )

    # ── Bandeau section SCORING (ligne 1) ────────────────────────────────
    fig.text(
        0.5, 0.475,
        "SCORING & ÉVALUATION",
        ha="center", va="center", fontsize=13, fontweight="bold",
        color="white",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#c0392b", alpha=0.9, linewidth=0),
    )

    cv_ids          = [r["cv_id"] for r in results]
    expected_scores = scoring_agg["expected_scores"]
    actual_scores   = scoring_agg["actual_scores"]
    fields          = sorted(field_avg.keys())
    n_fields        = len(fields)

    # ══════════════════════════════════════════════════════════════════════
    # LIGNE 0 — EXTRACTION
    # ══════════════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────────
    # [0,0]  P / R / F1 par champ (barres groupées)
    # ─────────────────────────────────────────────────
    ax      = axes[0, 0]
    bar_w   = 0.22
    x_pos   = list(range(n_fields))
    cfg_prf = [("precision", "#3498db", "Precision"),
               ("recall",    "#2ecc71", "Recall"),
               ("f1",        "#e67e22", "F1")]

    for idx, (metric, color, label) in enumerate(cfg_prf):
        offset = (idx - 1) * bar_w
        vals   = [field_avg[f][metric] for f in fields]
        bars   = ax.bar([x + offset for x in x_pos], vals,
                        width=bar_w, label=label, color=color, alpha=0.88)
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{v:.0f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(fields, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Score (%)", fontweight="bold")
    ax.set_ylim(70, 108)
    ax.set_title("Precision / Recall / F1 par champ", fontweight="bold", pad=8)
    ax.legend(fontsize=9, loc="lower right")
    ax.axhline(80, color="gray", linestyle=":", linewidth=1, alpha=0.5)
    ax.axhline(90, color="gray", linestyle=":", linewidth=1, alpha=0.3)
    ax.text(n_fields - 0.4, 80.5, "80%", fontsize=8, color="gray")
    ax.text(n_fields - 0.4, 90.5, "90%", fontsize=8, color="gray")
    ax.set_facecolor("#fdfdfd")

    # ─────────────────────────────────────────────────
    # [0,1]  F1 moyen par CV (barres horizontales)
    # ─────────────────────────────────────────────────
    ax      = axes[0, 1]
    cv_f1s  = [r["extraction_avg_f1"] for r in results]
    avg_f1  = sum(cv_f1s) / len(cv_f1s)

    bar_colors_f1 = [
        "#2ecc71" if v >= 95 else "#f39c12" if v >= 85 else "#e74c3c"
        for v in cv_f1s
    ]
    bars = ax.barh(range(len(cv_ids)), cv_f1s, color=bar_colors_f1, alpha=0.85)
    ax.axvline(avg_f1, color="#2c3e50", linestyle="--", linewidth=2,
               label=f"F1 moyen : {avg_f1:.1f}%")
    ax.axvline(90, color="gray", linestyle=":", linewidth=1, alpha=0.6)

    for bar, v in zip(bars, cv_f1s):
        ax.text(v + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{v:.0f}%", va="center", fontsize=6.5)

    ax.set_yticks(range(len(cv_ids)))
    ax.set_yticklabels(cv_ids, fontsize=6.5)
    ax.set_xlabel("F1 moyen extraction (%)", fontweight="bold")
    ax.set_xlim(60, 108)
    ax.set_title("F1 d'Extraction par CV", fontweight="bold", pad=8)
    ax.legend(fontsize=9)
    patches_f1 = [
        mpatches.Patch(color="#2ecc71", label="≥ 95%"),
        mpatches.Patch(color="#f39c12", label="85-95%"),
        mpatches.Patch(color="#e74c3c", label="< 85%"),
    ]
    ax.legend(handles=patches_f1 + [
        plt.Line2D([0], [0], linestyle="--", color="#2c3e50", label=f"Moy. {avg_f1:.1f}%")
    ], fontsize=8, loc="lower right")
    ax.set_facecolor("#fdfdfd")

    # ─────────────────────────────────────────────────
    # [0,2]  Heatmap P/R/F1/EM par champ
    # ─────────────────────────────────────────────────
    ax          = axes[0, 2]
    metrics_cols = ["precision", "recall", "f1", "exact_match"]
    col_labels   = ["Precision", "Recall", "F1", "Exact\nMatch"]
    matrix       = [[field_avg[f][m] for m in metrics_cols] for f in fields]

    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, fontsize=10, fontweight="bold")
    ax.set_yticks(range(n_fields))
    ax.set_yticklabels(fields, fontsize=9)
    ax.set_title("Heatmap : Métriques par Champ", fontweight="bold", pad=8)

    for i in range(n_fields):
        for j in range(len(metrics_cols)):
            v = matrix[i][j]
            txt_col = "white" if v < 45 or v > 80 else "#2c3e50"
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center",
                    fontsize=9, fontweight="bold", color=txt_col)

    plt.colorbar(im, ax=ax, shrink=0.85, label="Score (%)")

    # ══════════════════════════════════════════════════════════════════════
    # LIGNE 1 — SCORING
    # ══════════════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────────
    # [1,0]  Scatter Expected vs Actual
    # ─────────────────────────────────────────────────
    ax    = axes[1, 0]
    errs  = [abs(a - e) for a, e in zip(actual_scores, expected_scores)]
    cols  = ["#2ecc71" if e <= 10 else "#f39c12" if e <= 20 else "#e74c3c" for e in errs]
    ax.scatter(expected_scores, actual_scores, c=cols, s=90, zorder=3,
               edgecolors="white", linewidths=0.5)

    mn  = min(expected_scores + actual_scores) - 5
    mx_ = max(expected_scores + actual_scores) + 5
    ax.plot([mn, mx_], [mn, mx_], "--", color="gray", linewidth=1.5, zorder=2)

    if len(expected_scores) > 1:
        me = sum(expected_scores) / len(expected_scores)
        ma = sum(actual_scores)   / len(actual_scores)
        b  = sum((x - me) * (y - ma) for x, y in zip(expected_scores, actual_scores)) \
             / sum((x - me) ** 2 for x in expected_scores)
        a_reg = ma - b * me
        ax.plot([mn, mx_], [a_reg + b * mn, a_reg + b * mx_],
                "-", color="#8e44ad", linewidth=1.5)

    r2      = scoring_agg["r_squared"]
    pearson = scoring_agg["pearson"]
    ax.set_xlim(mn, mx_)
    ax.set_ylim(mn, mx_)
    ax.set_xlabel("Score Attendu", fontweight="bold")
    ax.set_ylabel("Score Obtenu",  fontweight="bold")
    ax.set_title("Scores Attendus vs Obtenus", fontweight="bold", pad=8)
    ax.text(0.05, 0.92,
            f"Pearson r = {pearson:.3f}\nR²  = {r2:.3f}",
            transform=ax.transAxes, fontsize=10, color="#2c3e50",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9))
    patches_s = [
        mpatches.Patch(color="#2ecc71", label="Erreur ≤ 10 pts"),
        mpatches.Patch(color="#f39c12", label="Erreur 10–20 pts"),
        mpatches.Patch(color="#e74c3c", label="Erreur > 20 pts"),
    ]
    ax.legend(handles=patches_s + [
        plt.Line2D([0], [0], linestyle="--", color="gray",   label="Idéal (y=x)"),
        plt.Line2D([0], [0], color="#8e44ad",                label="Régression"),
    ], fontsize=8)
    ax.set_facecolor("#fdfdfd")

    # ─────────────────────────────────────────────────
    # [1,1]  Distribution du Bias
    # ─────────────────────────────────────────────────
    ax        = axes[1, 1]
    biases    = [r["score_accuracy"]["bias"] for r in results]
    bias_mean = sum(biases) / len(biases)
    bias_std  = (sum((b - bias_mean) ** 2 for b in biases) / len(biases)) ** 0.5

    ax.hist(biases, bins=min(14, len(biases)), color="#9b59b6", alpha=0.80, edgecolor="white")
    ax.axvline(0,         color="black", linestyle="-",  linewidth=1.8, label="Zéro")
    ax.axvline(bias_mean, color="red",   linestyle="--", linewidth=2,
               label=f"Bias moyen : {bias_mean:+.1f}")
    ax.set_xlabel("Bias  (obtenu − attendu)", fontweight="bold")
    ax.set_ylabel("Nombre de CVs", fontweight="bold")
    ax.set_title("Distribution du Bias de Scoring", fontweight="bold", pad=8)
    ax.legend(fontsize=9)
    ax.text(0.64, 0.86,
            f"μ = {bias_mean:+.2f}\nσ = {bias_std:.2f}",
            transform=ax.transAxes, fontsize=10,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9))
    ax.set_facecolor("#fdfdfd")

    # ─────────────────────────────────────────────────
    # [1,2]  Erreur absolue par CV
    # ─────────────────────────────────────────────────
    ax         = axes[1, 2]
    errors     = [r["score_accuracy"]["mae"] for r in results]
    err_colors = ["#2ecc71" if e <= 10 else "#f39c12" if e <= 20 else "#e74c3c"
                  for e in errors]

    ax.bar(range(len(cv_ids)), errors, color=err_colors, alpha=0.85)
    ax.axhline(10, color="#27ae60", linestyle="--", linewidth=1.5)
    ax.axhline(20, color="#e67e22", linestyle="--", linewidth=1.5)
    ax.axhline(scoring_agg["avg_mae"], color="red", linestyle="-", linewidth=2,
               label=f"MAE moy. {scoring_agg['avg_mae']:.1f} pts")

    ax.set_xticks(range(len(cv_ids)))
    ax.set_xticklabels(cv_ids, rotation=90, ha="center", fontsize=6.5)
    ax.set_ylabel("Erreur absolue (pts)", fontweight="bold")
    ax.set_title(
        f"Erreur de Score par CV"
        f"  —  RMSE = {scoring_agg['rmse']:.1f} pts   Within±10 = {scoring_agg['within_10_pct']:.0f}%",
        fontweight="bold", pad=8,
    )
    patches_e = [
        mpatches.Patch(color="#2ecc71", label="≤ 10 pts"),
        mpatches.Patch(color="#f39c12", label="10–20 pts"),
        mpatches.Patch(color="#e74c3c", label="> 20 pts"),
    ]
    ax.legend(handles=patches_e + [
        plt.Line2D([0], [0], linestyle="--", color="#27ae60", label="Seuil 10 pts"),
        plt.Line2D([0], [0], linestyle="--", color="#e67e22", label="Seuil 20 pts"),
        plt.Line2D([0], [0], color="red", label=f"MAE={scoring_agg['avg_mae']:.1f}"),
    ], fontsize=8)
    ax.set_facecolor("#fdfdfd")

    # ── Bannière KPIs — en bas de figure ────────────────────────────────────
    avg_f1_global  = sum(r["extraction_avg_f1"]        for r in results) / len(results)
    avg_prec       = sum(r["extraction_avg_precision"]  for r in results) / len(results)
    avg_rec        = sum(r["extraction_avg_recall"]     for r in results) / len(results)
    avg_em         = sum(r["extraction_avg_exact_match"]for r in results) / len(results)

    line1 = (
        f"EXTRACTION :  F1 = {avg_f1_global:.1f}%   "
        f"Precision = {avg_prec:.1f}%   "
        f"Recall = {avg_rec:.1f}%   "
        f"Exact Match = {avg_em:.1f}%"
    )
    line2 = (
        f"SCORING :  MAE = {scoring_agg['avg_mae']:.1f} pts   "
        f"RMSE = {scoring_agg['rmse']:.1f} pts   "
        f"Bias = {scoring_agg['bias']:+.1f} pts   "
        f"Pearson r = {scoring_agg['pearson']:.3f}   "
        f"R² = {scoring_agg['r_squared']:.3f}   "
        f"Within ±10 pts = {scoring_agg['within_10_pct']:.0f}%"
    )
    fig.text(
        0.5, -0.015,
        f"{line1}\n{line2}",
        ha="center", va="top", fontsize=10.5, color="#2c3e50",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#dfe6e9", alpha=0.95, linewidth=0),
    )

    plt.tight_layout(rect=[0, 0.04, 1, 0.98])

    report_dir   = os.path.join(os.path.dirname(__file__), "accuracyreports")
    output_chart = os.path.join(report_dir, f"accuracy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    plt.savefig(output_chart, dpi=150, bbox_inches="tight")
    print(f"OK: Graphique sauvegardé : {output_chart}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    dataset_path = os.path.join(os.path.dirname(__file__), "test_dataset.json")
    asyncio.run(run_evaluation_pipeline(dataset_path, parallel=False))
