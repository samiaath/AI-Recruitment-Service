import asyncio
from datetime import datetime
from ..database.db_connection import get_db_connection
from ..models import ExtractedApplicationData
import re
import os
import uuid


# ═══════════════════════════════════════════════════════════════
# SAFE HELPERS
# ═══════════════════════════════════════════════════════════════

def _trunc(value, max_len):
    if value is None:
        return None
    return str(value)[:max_len]


def _safe_required(value, fallback: str):
    if value is None or str(value).strip() == "":
        return fallback
    return str(value)


def _safe_date(value, fallback="0000-01"):
    if not value:
        return fallback
    return str(value)


# ═══════════════════════════════════════════════════════════════
# INSTITUTION RESOLUTION
# ═══════════════════════════════════════════════════════════════

def _resolve_or_create_institution(cursor, institution_id, institution_name, description):
    if institution_id:
        cursor.execute("SELECT InstitutionID FROM Institution WHERE InstitutionID = ?", (institution_id,))
        row = cursor.fetchone()
        if row:
            return row[0]

    inst_name = institution_name

    if not inst_name and description:
        patterns = [
            r"(?:Université|Institut|École|ENSI|ESPRIT|INSAT)[A-Za-zÀ-ÿ\s\-]*",
            r"\b([A-Z]{2,})\b"
        ]
        for p in patterns:
            m = re.search(p, description)
            if m:
                inst_name = m.group(0)
                break

    if not inst_name:
        return 1  # UNKNOWN INSTITUTION ID

    cursor.execute(
        "SELECT TOP 1 InstitutionID FROM Institution WHERE InstitutionLabel LIKE ?",
        (f"%{inst_name}%",)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    acronym = "".join([c[0] for c in inst_name.split() if c]).upper()[:10] or "UNK"

    cursor.execute(
        """
        INSERT INTO Institution
        (InstitutionAcronym, InstitutionLabel, InstitutionRank, InstitutionStatus)
        OUTPUT INSERTED.InstitutionID
        VALUES (?, ?, 0, 1)
        """,
        (acronym, inst_name[:100])
    )

    return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════════
# STUDY LEVEL RESOLUTION
# ═══════════════════════════════════════════════════════════════

def _resolve_or_create_study_level(cursor, study_level_id, study_level_name, description):
    if study_level_id:
        cursor.execute("SELECT StudyLevelID FROM StudyLevel WHERE StudyLevelID = ?", (study_level_id,))
        row = cursor.fetchone()
        if row:
            return row[0]

    level_name = study_level_name
    rank = 0

    if not level_name and description:
        mapping = {
            r"bac\+2|bts|dut": ("Bac+2", 1),
            r"bac\+3|licence|bachelor": ("Bac+3", 2),
            r"bac\+5|master|ingénieur": ("Bac+5", 3),
            r"bac\+8|phd|doctorat": ("Bac+8", 4),
        }

        desc = description.lower()
        for p, (name, r) in mapping.items():
            if re.search(p, desc):
                level_name = name
                rank = r
                break

    if not level_name:
        return 1  # UNKNOWN LEVEL ID

    cursor.execute(
        "SELECT TOP 1 StudyLevelID FROM StudyLevel WHERE StudyLevelLabel LIKE ?",
        (f"%{level_name}%",)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO StudyLevel
        (StudyLevelLabel, StudyLevelRank, StudyLevelStatus)
        OUTPUT INSERTED.StudyLevelID
        VALUES (?, ?, 1)
        """,
        (level_name[:50], rank)
    )

    return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════════
# UPDATE APPLICATION
# ═══════════════════════════════════════════════════════════════

def _sync_update_application_score(application_id, score, explanation, ai_data):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Candidate check
            cursor.execute(
                "SELECT ApplicationCandidateID, ApplicationStatus FROM Application WHERE ApplicationID = ?",
                (application_id,)
            )
            row = cursor.fetchone()

            if row and row[0] and row[1] in (1, 'pending', 'Pending'):
                candidate_id = row[0]
                c = ai_data.candidate

                cursor.execute(
                    "SELECT ApplicationCandidateName, ApplicationCandidateBirthDate, ApplicationCandidatePhone1, ApplicationCandidatePhone2, ApplicationCandidateAddress FROM Candidate WHERE CandidateID = ?",
                    (candidate_id,)
                )
                existing = cursor.fetchone()

                updates = []
                values = []

                if c.ApplicationCandidateName and not existing[0]:
                    updates.append("ApplicationCandidateName=?")
                    values.append(_trunc(c.ApplicationCandidateName, 50))

                if c.ApplicationCandidateBirthDate and not existing[1]:
                    updates.append("ApplicationCandidateBirthDate=?")
                    values.append(_trunc(c.ApplicationCandidateBirthDate, 15))

                if c.ApplicationCandidatePhone1 and not existing[2]:
                    updates.append("ApplicationCandidatePhone1=?")
                    values.append(_trunc(c.ApplicationCandidatePhone1, 20))

                if c.ApplicationCandidatePhone2 and not existing[3]:
                    updates.append("ApplicationCandidatePhone2=?")
                    values.append(_trunc(c.ApplicationCandidatePhone2, 20))

                if c.ApplicationCandidateAddress and not existing[4]:
                    updates.append("ApplicationCandidateAddress=?")
                    values.append(_trunc(c.ApplicationCandidateAddress, 50))

                if updates:
                    cursor.execute(
                        f"UPDATE Candidate SET {', '.join(updates)} WHERE CandidateID=?",
                        (*values, candidate_id)
                    )

            # Application update
            cursor.execute(
                """
                UPDATE Application
                SET ApplicationPreselectionScore = ?,
                    status_ai = 'done',
                    ApplicationEvaluationExplanation = ?
                WHERE ApplicationID = ?
                """,
                (round(score, 2), _trunc(explanation, 1000), application_id)
            )

            # cleanup
            cursor.execute("DELETE FROM Skill WHERE SkillApplicationID=?", (application_id,))
            cursor.execute("DELETE FROM Experience WHERE ExperienceApplicationID=?", (application_id,))
            cursor.execute("DELETE FROM ApplicationDegree WHERE DegreeApplicationID=?", (application_id,))

           # Skills
            for s in ai_data.skills:
                if s.SkillDescription:
                    cursor.execute(
                        "INSERT INTO Skill (SkillDescription, SkillApplicationID) VALUES (?, ?)",
                        (_trunc(s.SkillDescription, 100), application_id)
                    )

            # Experiences
            for e in ai_data.experiences:
                cursor.execute(
                    "INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID) VALUES (?, ?, ?, ?, ?)",
                    (
                        _safe_date(e.ExperienceStartDate),
                        _safe_date(e.ExperienceEndDate, "present"),
                        _safe_required(e.ExperienceCompany, "Unknown Company")[:50],
                        _safe_required(e.ExperiencePosition, "Unknown Role")[:50],
                        application_id
                    )
                )

            # Degrees
            for d in ai_data.degrees:
                inst = _resolve_or_create_institution(cursor, d.institution_id, d.institution_name, d.Description)
                lvl = _resolve_or_create_study_level(cursor, d.study_level_id, d.study_level_name, d.Description)

                cursor.execute(
                    """
                    INSERT INTO ApplicationDegree
                    (DegreeObtentionYear, DegreeApplicationID, DegreeInstitutionID, DegreeStudyLevelID, Description)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        _safe_required(d.DegreeObtentionYear, "0000")[:4],
                        application_id,
                        inst,
                        lvl,
                        _trunc(d.Description, 100)
                    )
                )

            print(f"[UPDATER] Updated application {application_id}")

    except Exception as e:
        print(f"[UPDATER ERROR] {e}")


async def update_application_score(application_id, score, explanation, ai_data):
    await asyncio.to_thread(_sync_update_application_score, application_id, score, explanation, ai_data)