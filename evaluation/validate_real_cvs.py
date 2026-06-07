"""
Validation sur CVs Réels — Sans annotation complète
====================================================
Objectif : mesurer la qualité d'extraction sur des CVs réels de production
(dossier CVs/) qui n'ont jamais été vus lors de l'optimisation du système.

Deux métriques sans annotation :
  1. Taux de complétude  : champs non-null extraits (nom, email, phone, skills, exp, degrees)
  2. Taux de cohérence   : valeurs extraites qui "ont du sens" (email valide, phone valide, etc.)

Métrique avec annotation manuelle partielle :
  3. Spot-check accuracy : vérification humaine sur 15 CVs (nom/email/phone/1 expérience/1 diplôme)
     → Remplir la colonne "human_ok" dans le CSV exporté (1=correct, 0=erreur)
"""

import asyncio
import csv
import json
import os
import re
import sys
import time
from datetime import datetime

# Console Windows : forcer UTF-8 pour éviter les erreurs cp1252
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ai_service.processing.file_handler import process_file
from ai_service.processing.cleaner import clean_text
from ai_service.ai.analyzer import analyze_candidate

# Job description générique pour tester le scoring sur les CVs IT
JOB_IT_GENERIC = (
    "Développeur ou ingénieur informatique. "
    "Compétences techniques en programmation, bases de données, outils de développement. "
    "Expérience professionnelle ou stage en entreprise appréciée."
)


def _is_valid_email(email: str | None) -> bool:
    if not email:
        return False
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))


def _is_valid_phone(phone: str | None) -> bool:
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 7


async def validate_single_cv(cv_path: str) -> dict:
    filename = os.path.basename(cv_path)
    start = time.time()

    try:
        raw_text    = await process_file(cv_path)
        cleaned     = clean_text(raw_text)
        email_meta  = {
            "PositionReference": "VALIDATION-REELLE",
            "PositionDescription": JOB_IT_GENERIC,
        }
        extracted   = await analyze_candidate(cleaned, raw_text, email_meta)
        elapsed     = round(time.time() - start, 2)

        c = extracted.candidate
        skills_count = sum(len(sg.skills) for sg in extracted.skills)
        exp_count    = len(extracted.experiences)
        deg_count    = len(extracted.degrees)
        total_xp     = extracted.total_years_experience or 0.0

        # ── Complétude ──────────────────────────────────────────────────
        fields_present = {
            "nom":      1 if c.ApplicationCandidateName  else 0,
            "email":    1 if c.ApplicationEmail          else 0,
            "phone":    1 if c.ApplicationCandidatePhone1 else 0,
            "skills":   1 if skills_count > 0            else 0,
            "exp":      1 if exp_count > 0               else 0,
            "degrees":  1 if deg_count > 0               else 0,
        }
        completeness = round(sum(fields_present.values()) / len(fields_present) * 100, 1)

        # ── Cohérence ───────────────────────────────────────────────────
        coherence_checks = {
            "email_valide":   1 if _is_valid_email(c.ApplicationEmail)            else 0,
            "phone_valide":   1 if _is_valid_phone(c.ApplicationCandidatePhone1)  else 0,
            "nom_longueur":   1 if (c.ApplicationCandidateName or "")and len(c.ApplicationCandidateName or "") >= 3 else 0,
            "skills_pluriel": 1 if skills_count >= 2                              else 0,
            "xp_coherente":   1 if 0 <= total_xp <= 50                           else 0,
        }
        coherence = round(sum(coherence_checks.values()) / len(coherence_checks) * 100, 1)

        # Résumé lisible pour le spot-check manuel
        first_exp = ""
        if extracted.experiences:
            e = extracted.experiences[0]
            first_exp = f"{e.ExperiencePosition or '?'} @ {e.ExperienceCompany or '?'}"

        first_deg = ""
        if extracted.degrees:
            d = extracted.degrees[0]
            first_deg = d.DegreeLabel[:50] if d.DegreeLabel else "?"

        top_skills = ", ".join(
            s for sg in extracted.skills[:2] for s in sg.skills[:3]
        )

        return {
            "fichier":       filename,
            "nom_extrait":   c.ApplicationCandidateName or "",
            "email_extrait": c.ApplicationEmail or "",
            "phone_extrait": c.ApplicationCandidatePhone1 or "",
            "nb_skills":     skills_count,
            "top_skills":    top_skills[:80],
            "nb_experiences":exp_count,
            "premiere_exp":  first_exp[:80],
            "nb_diplomes":   deg_count,
            "premier_diplome": first_deg,
            "total_xp_ans":  total_xp,
            "completude_%":  completeness,
            "coherence_%":   coherence,
            "temps_s":       elapsed,
            # ── COLONNES À REMPLIR MANUELLEMENT (spot-check) ──────────────
            # Pour chaque champ extrait : 1 = correct, 0 = incorrect, vide = champ absent du CV / non vérifié
            "nom_ok":        "",
            "email_ok":      "",
            "phone_ok":      "",
            "skills_ok":     "",
            "exp_ok":        "",
            "deg_ok":        "",
            # Champs PRÉSENTS dans le CV mais MANQUÉS par le système (pour le recall)
            # Lister séparés par virgule parmi : nom,email,phone,skills,exp,deg  (vide = rien manqué)
            "champs_manques": "",
            "commentaire":   "",
            "statut":        "OK",
        }

    except Exception as ex:
        return {
            "fichier":        filename,
            "nom_extrait":    "",
            "email_extrait":  "",
            "phone_extrait":  "",
            "nb_skills":      0,
            "top_skills":     "",
            "nb_experiences": 0,
            "premiere_exp":   "",
            "nb_diplomes":    0,
            "premier_diplome": "",
            "total_xp_ans":   0.0,
            "completude_%":   0.0,
            "coherence_%":    0.0,
            "temps_s":        round(time.time() - start, 2),
            "nom_ok":         "",
            "email_ok":       "",
            "phone_ok":       "",
            "skills_ok":      "",
            "exp_ok":         "",
            "deg_ok":         "",
            "champs_manques": "",
            "commentaire":    str(ex)[:100],
            "statut":         "ERREUR",
        }


async def run_real_cv_validation(cv_dir: str = None):
    if cv_dir is None:
        cv_dir = os.path.join(ROOT, "CVs")

    cv_files = [
        os.path.join(cv_dir, f)
        for f in os.listdir(cv_dir)
        if f.lower().endswith((".pdf", ".docx", ".doc"))
    ]
    cv_files.sort()

    print(f"\n{'='*65}")
    print(f"  VALIDATION SUR CVs RÉELS — {len(cv_files)} fichiers")
    print(f"{'='*65}")

    results = []
    for i, path in enumerate(cv_files, 1):
        print(f"[{i:02d}/{len(cv_files)}] {os.path.basename(path)[:50]}", end="  ")
        r = await validate_single_cv(path)
        status = "[OK]" if r["statut"] == "OK" else "[ERREUR]"
        print(f"{status}  completude={r['completude_%']}%  coherence={r['coherence_%']}%  ({r['temps_s']}s)")
        results.append(r)

    # ── Statistiques agrégées ────────────────────────────────────────────
    ok = [r for r in results if r["statut"] == "OK"]
    n  = len(ok)

    if n == 0:
        print("Aucun CV traité avec succès.")
        return

    avg_completude = sum(r["completude_%"] for r in ok) / n
    avg_coherence  = sum(r["coherence_%"]  for r in ok) / n
    avg_temps      = sum(r["temps_s"]      for r in ok) / n

    rate_nom    = sum(1 for r in ok if r["nom_extrait"])    / n * 100
    rate_email  = sum(1 for r in ok if r["email_extrait"])  / n * 100
    rate_phone  = sum(1 for r in ok if r["phone_extrait"])  / n * 100
    rate_skills = sum(1 for r in ok if r["nb_skills"] > 0)  / n * 100
    rate_exp    = sum(1 for r in ok if r["nb_experiences"] > 0) / n * 100
    rate_deg    = sum(1 for r in ok if r["nb_diplomes"] > 0)/ n * 100

    print(f"\n{'='*65}")
    print(f"  RAPPORT — {n}/{len(results)} CVs traités avec succès")
    print(f"{'='*65}")
    print(f"  Complétude moyenne   : {avg_completude:.1f}%")
    print(f"  Cohérence moyenne    : {avg_coherence:.1f}%")
    print(f"  Temps moyen          : {avg_temps:.2f}s")
    print(f"\n  Taux d'extraction par champ :")
    print(f"    Nom              : {rate_nom:.0f}%")
    print(f"    Email            : {rate_email:.0f}%")
    print(f"    Téléphone        : {rate_phone:.0f}%")
    print(f"    Compétences      : {rate_skills:.0f}%")
    print(f"    Expériences      : {rate_exp:.0f}%")
    print(f"    Diplômes         : {rate_deg:.0f}%")

    # ── Export CSV pour spot-check manuel ────────────────────────────────
    out_dir  = os.path.dirname(__file__)
    out_csv  = os.path.join(out_dir, f"validation_reelle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    out_json = os.path.join(out_dir, f"validation_reelle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    fieldnames = list(results[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_cvs":  len(results),
            "successful": n,
            "summary": {
                "avg_completude": round(avg_completude, 2),
                "avg_coherence":  round(avg_coherence,  2),
                "avg_temps_s":    round(avg_temps,       2),
                "taux_nom":       round(rate_nom,   1),
                "taux_email":     round(rate_email, 1),
                "taux_phone":     round(rate_phone, 1),
                "taux_skills":    round(rate_skills,1),
                "taux_exp":       round(rate_exp,   1),
                "taux_degrees":   round(rate_deg,   1),
            },
            "details": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  CSV exporté : {out_csv}")
    print(f"  JSON exporté: {out_json}")
    print(f"\n  PROCHAINE ÉTAPE — Spot-check manuel (~30 min sur 15 CVs) :")
    print(f"  1. Ouvrir le CSV. Pour chaque CV vérifié, comparer les colonnes")
    print(f"     'nom_extrait/email_extrait/...' au CV réel.")
    print(f"  2. Remplir nom_ok, email_ok, phone_ok, skills_ok, exp_ok, deg_ok")
    print(f"     -> 1 = correct | 0 = incorrect | vide = champ absent du CV.")
    print(f"  3. Si le système a MANQUÉ un champ présent dans le CV, le lister")
    print(f"     dans 'champs_manques' (ex: phone,deg).")
    print(f"  4. Lancer : python evaluation/score_real_cvs.py <chemin_du_csv>")
    print(f"     -> calcule Precision / Recall / F1 terrain par champ et global.\n")


if __name__ == "__main__":
    asyncio.run(run_real_cv_validation())
