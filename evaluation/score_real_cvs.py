"""
Calcul du F1 terrain sur CVs réels (à partir du spot-check manuel)
==================================================================
Lit un CSV produit par validate_real_cvs.py et rempli à la main, puis calcule
Precision / Recall / F1 par champ et global, sur l'échantillon vérifié.

MÉTHODE (honnête, adaptée à un spot-check sans vérité terrain exhaustive) :

  Pour chaque champ (nom, email, phone, skills, exp, deg) :
    - VP (vrai positif)  : champ extrait ET jugé correct      (<champ>_ok = 1)
    - FP (faux positif)  : champ extrait MAIS jugé incorrect   (<champ>_ok = 0)
    - FN (faux négatif)  : champ présent dans le CV mais MANQUÉ (listé dans 'champs_manques')

    Precision = VP / (VP + FP)   -> parmi ce qui est extrait, combien est correct
    Recall    = VP / (VP + FN)   -> parmi ce qui aurait dû l'être, combien est trouvé
    F1        = 2·P·R / (P + R)

  Les cellules <champ>_ok vides (champ absent du CV) sont ignorées : ni VP, ni FP, ni FN.

USAGE :
    python evaluation/score_real_cvs.py evaluation/validation_reelle_AAAAMMJJ_HHMMSS.csv
    (si aucun argument : prend le CSV le plus récent du dossier evaluation/)
"""

import csv
import glob
import json
import os
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FIELDS = ["nom", "email", "phone", "skills", "exp", "deg"]
FIELD_LABELS = {
    "nom":    "Nom",
    "email":  "Email",
    "phone":  "Téléphone",
    "skills": "Compétences",
    "exp":    "Expériences",
    "deg":    "Diplômes",
}


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_csv(csv_path: str):
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # Compteurs par champ
    counts = {fld: {"VP": 0, "FP": 0, "FN": 0} for fld in FIELDS}
    n_verified_rows = 0

    for row in rows:
        # Une ligne est "vérifiée" si au moins un <champ>_ok est rempli
        ok_values = {fld: (row.get(f"{fld}_ok", "") or "").strip() for fld in FIELDS}
        if not any(v in ("0", "1") for v in ok_values.values()):
            continue
        n_verified_rows += 1

        # VP / FP depuis les colonnes <champ>_ok
        for fld in FIELDS:
            v = ok_values[fld]
            if v == "1":
                counts[fld]["VP"] += 1
            elif v == "0":
                counts[fld]["FP"] += 1
            # vide -> ignoré

        # FN depuis 'champs_manques'
        missed = (row.get("champs_manques", "") or "").strip().lower()
        if missed:
            for token in missed.replace(";", ",").split(","):
                token = token.strip()
                if token in counts:
                    counts[token]["FN"] += 1

    if n_verified_rows == 0:
        print("\n[!] Aucune ligne vérifiée trouvée.")
        print("    Remplis les colonnes nom_ok/email_ok/... (1/0) dans le CSV puis relance.\n")
        return

    # ── Calcul par champ ──────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  F1 TERRAIN SUR CVs RÉELS  —  {n_verified_rows} CVs vérifiés")
    print(f"  Source : {os.path.basename(csv_path)}")
    print(f"{'='*70}")
    print(f"  {'Champ':<14} {'VP':>4} {'FP':>4} {'FN':>4} {'Precision':>10} {'Recall':>8} {'F1':>8}")
    print(f"  {'-'*14} {'-'*4} {'-'*4} {'-'*4} {'-'*10} {'-'*8} {'-'*8}")

    field_metrics = {}
    sum_p = sum_r = sum_f = 0.0
    n_fields_with_data = 0

    glob_vp = glob_fp = glob_fn = 0

    for fld in FIELDS:
        vp, fp, fn = counts[fld]["VP"], counts[fld]["FP"], counts[fld]["FN"]
        if vp + fp + fn == 0:
            continue
        p = vp / (vp + fp) if (vp + fp) else 0.0
        r = vp / (vp + fn) if (vp + fn) else 0.0
        f = _f1(p, r)
        field_metrics[fld] = {
            "VP": vp, "FP": fp, "FN": fn,
            "precision": round(p * 100, 1),
            "recall":    round(r * 100, 1),
            "f1":        round(f * 100, 1),
        }
        print(f"  {FIELD_LABELS[fld]:<14} {vp:>4} {fp:>4} {fn:>4} "
              f"{p*100:>9.1f}% {r*100:>7.1f}% {f*100:>7.1f}%")
        sum_p += p; sum_r += r; sum_f += f
        n_fields_with_data += 1
        glob_vp += vp; glob_fp += fp; glob_fn += fn

    # ── Global ────────────────────────────────────────────────────────────
    # Macro (moyenne des F1 par champ) + Micro (sur l'ensemble des décisions)
    macro_p = sum_p / n_fields_with_data * 100
    macro_r = sum_r / n_fields_with_data * 100
    macro_f = sum_f / n_fields_with_data * 100

    micro_p = glob_vp / (glob_vp + glob_fp) * 100 if (glob_vp + glob_fp) else 0.0
    micro_r = glob_vp / (glob_vp + glob_fn) * 100 if (glob_vp + glob_fn) else 0.0
    micro_f = _f1(micro_p / 100, micro_r / 100) * 100

    print(f"  {'-'*14} {'-'*4} {'-'*4} {'-'*4} {'-'*10} {'-'*8} {'-'*8}")
    print(f"  {'MACRO (moy.)':<14} {'':>4} {'':>4} {'':>4} "
          f"{macro_p:>9.1f}% {macro_r:>7.1f}% {macro_f:>7.1f}%")
    print(f"  {'MICRO (global)':<14} {glob_vp:>4} {glob_fp:>4} {glob_fn:>4} "
          f"{micro_p:>9.1f}% {micro_r:>7.1f}% {micro_f:>7.1f}%")

    print(f"\n  >> F1 TERRAIN (macro) : {macro_f:.1f}%")
    print(f"  >> À comparer au F1 du dataset annoté : 97.5%")
    print(f"{'='*70}\n")

    # ── Export JSON ───────────────────────────────────────────────────────
    out = {
        "timestamp": datetime.now().isoformat(),
        "source_csv": os.path.basename(csv_path),
        "cvs_verifies": n_verified_rows,
        "par_champ": field_metrics,
        "global": {
            "macro_precision": round(macro_p, 1),
            "macro_recall":    round(macro_r, 1),
            "macro_f1":        round(macro_f, 1),
            "micro_precision": round(micro_p, 1),
            "micro_recall":    round(micro_r, 1),
            "micro_f1":        round(micro_f, 1),
        },
    }
    out_path = os.path.join(
        os.path.dirname(csv_path),
        f"f1_terrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"  Résultat sauvegardé : {out_path}\n")


def _latest_csv():
    pattern = os.path.join(os.path.dirname(__file__), "validation_reelle_*.csv")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = _latest_csv()
        if path:
            print(f"[i] Aucun argument fourni — CSV le plus récent : {os.path.basename(path)}")

    if not path or not os.path.exists(path):
        print("Usage : python evaluation/score_real_cvs.py <chemin_du_csv>")
        sys.exit(1)

    score_csv(path)
