import asyncio
from datetime import datetime
from ..database.db_connection import get_db_connection
from ..models import ExtractedApplicationData


# ══════════════════════════════════════════════════════════════════════════════
# Résolution Institution/StudyLevel avec insertion auto et récupération PK
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_or_create_institution(cursor, institution_id: int | None, institution_name: str | None, description: str | None) -> int | None:
    """
    Si institution_id fourni → vérifie existence, sinon insère, retourne PK
    Si institution_id null → utilise institution_name si dispo, sinon extrait depuis Description, cherche/crée, retourne PK
    """
    # Cas 1 : ID fourni par Mistral
    if institution_id is not None:
        cursor.execute("SELECT InstitutionID FROM Institution WHERE InstitutionID = ?", (institution_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        print(f"[UPDATER] Institution ID {institution_id} introuvable en DB, fallback vers le nom...")

    # Cas 2 : Pas d'ID → utilisation du nom fourni ou extraction depuis Description
    inst_name = institution_name
    if not inst_name and description and description.strip():
        # Heuristique : cherche nom d'institution dans la description
        import re
        patterns = [
            r"(?:à l'|à |de l'|de la |de |à la )([A-ZÀ-Ü][A-Za-zÀ-ÿ\s\-]+(?:Université|ENSI|ESPRIT|INSAT|Polytechnique|École|Institut|Lycée)[A-Za-zÀ-ÿ\s\-]*)",
            r"([A-ZÀ-Ü][A-Z]{2,})",  # Acronymes type ENSI, MIT, ESPRIT
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                inst_name = match.group(1).strip()
                break
    
    if not inst_name:
        print(f"[UPDATER] Impossible d'extraire institution")
        return None

    # Recherche en DB (LIKE pour flexibilité)
    cursor.execute(
        "SELECT TOP 1 InstitutionID FROM Institution WHERE InstitutionLabel LIKE ?",
        (f"%{inst_name}%",)
    )
    row = cursor.fetchone()
    if row:
        print(f"[UPDATER] Institution trouvée : {inst_name} → ID {row[0]}")
        return row[0]

    # Création nouvelle institution
    acronym = "".join([c[0] for c in inst_name.split() if c[0].isupper()])[:10] or inst_name[:10]
    cursor.execute(
        "INSERT INTO Institution (InstitutionAcronym, InstitutionLabel, InstitutionRank, InstitutionStatus) OUTPUT INSERTED.InstitutionID VALUES (?, ?, 0, 1)",
        (acronym, inst_name[:100])
    )
    new_id = int(cursor.fetchone()[0])
    print(f"[UPDATER] Institution créée : {inst_name} → ID {new_id}")
    return new_id


def _resolve_or_create_study_level(cursor, study_level_id: int | None, study_level_name: str | None, description: str | None) -> int | None:
    """
    Si study_level_id fourni → vérifie existence, retourne PK
    Si null → utilise study_level_name si fourni, sinon extrait depuis Description, cherche/crée, retourne PK
    """
    # Cas 1 : ID fourni
    if study_level_id is not None:
        cursor.execute("SELECT StudyLevelID FROM StudyLevel WHERE StudyLevelID = ?", (study_level_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        print(f"[UPDATER] StudyLevel ID {study_level_id} introuvable, fallback vers le nom...")

    # Cas 2 : Utilisation du nom fourni ou Extraction depuis Description
    level_name = study_level_name
    level_rank = 0

    if not level_name and description and description.strip():
        import re
        mapping = {
            r"bac\+?2|bts|dut|licence 1|l1|deug": ("Bac+2", 1),
            r"bac\+?3|licence|bachelor": ("Bac+3 (Licence)", 2),
            r"bac\+?5|master|ingénieur|diplôme d'ingénieur": ("Bac+5 (Master/Ingénieur)", 3),
            r"bac\+?8|doctorat|phd": ("Bac+8 (Doctorat)", 4),
        }
        
        desc_lower = description.lower()
        for pattern, (name, rank) in mapping.items():
            if re.search(pattern, desc_lower):
                level_name = name
                level_rank = rank
                break
    
    if not level_name:
        print(f"[UPDATER] Niveau d'études non détecté")
        return None

    # Recherche en DB
    cursor.execute(
        "SELECT TOP 1 StudyLevelID FROM StudyLevel WHERE StudyLevelLabel LIKE ?",
        (f"%{level_name}%",)
    )
    row = cursor.fetchone()
    if row:
        print(f"[UPDATER] StudyLevel trouvé : {level_name} → ID {row[0]}")
        return row[0]

    # Création
    cursor.execute(
        "INSERT INTO StudyLevel (StudyLevelLabel, StudyLevelScore, StudyLevelStatus) OUTPUT INSERTED.StudyLevelID VALUES (?, ?, 1)",
        (level_name[:50], level_rank)
    )
    new_id = int(cursor.fetchone()[0])
    print(f"[UPDATER] StudyLevel créé : {level_name} → ID {new_id}")
    return new_id


# ══════════════════════════════════════════════════════════════════════════════
# UPDATE — Candidature existante
# ══════════════════════════════════════════════════════════════════════════════

def _sync_update_application_score(
    application_id: int,
    score: float,
    explanation: str,
    ai_data: ExtractedApplicationData
):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Application SET ApplicationPreselectionScore = ?, status_ai = 'done', ApplicationEvaluationExplanation = ? WHERE ApplicationID = ?",
                (round(score, 2), _trunc(explanation, 1000), application_id)
            )
            cursor.execute("DELETE FROM Skill WHERE SkillApplicationID = ?", (application_id,))
            cursor.execute("DELETE FROM Experience WHERE ExperienceApplicationID = ?", (application_id,))
            cursor.execute("DELETE FROM ApplicationDegree WHERE DegreeApplicationID = ?", (application_id,))

            for skill in ai_data.skills:
                if skill.SkillDescription and skill.SkillDescription.strip():
                    cursor.execute(
                        "INSERT INTO Skill (SkillDescription, SkillApplicationID) VALUES (?, ?)",
                        (skill.SkillDescription[:100], application_id)
                    )

            for exp in ai_data.experiences:
                cursor.execute(
                    "INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID) VALUES (?, ?, ?, ?, ?)",
                    (_trunc(exp.ExperienceStartDate, 10), _trunc(exp.ExperienceEndDate, 10), _trunc(exp.ExperienceCompany, 50), _trunc(exp.ExperiencePosition, 50), application_id)
                )

            for deg in ai_data.degrees:
                inst_pk = _resolve_or_create_institution(cursor, deg.institution_id, deg.institution_name, deg.Description)
                sl_pk   = _resolve_or_create_study_level(cursor, deg.study_level_id, deg.study_level_name, deg.Description)
                
                # MAJ Object Python Json
                deg.institution_id = inst_pk
                deg.study_level_id = sl_pk
                
                cursor.execute(
                    "INSERT INTO ApplicationDegree (DegreeObtentionYear, DegreeApplicationID, DegreeInstitutionID, DegreeStudyLevelID, Description) VALUES (?, ?, ?, ?, ?)",
                    (_trunc(deg.DegreeObtentionYear, 4), application_id, inst_pk, sl_pk, _trunc(deg.Description, 100))
                )

            print(f"[UPDATER] ApplicationID={application_id} mis à jour")
    except Exception as e:
        print(f"[UPDATER] Erreur UPDATE : {e}")


async def update_application_score(application_id, score, explanation, ai_data):
    await asyncio.to_thread(_sync_update_application_score, application_id, score, explanation, ai_data)


# ══════════════════════════════════════════════════════════════════════════════
# INSERT — Nouveau candidat
# ══════════════════════════════════════════════════════════════════════════════

def _sync_insert_new_candidate_and_application(ai_data, score, explanation, session_position_id, cv_path):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            c = ai_data.candidate
            
            # Vérifier si le candidat existe déjà (via Email ou Phone)
            candidate_id = None
            if c.ApplicationEmail:
                cursor.execute("SELECT TOP 1 CandidateID FROM Candidate WHERE ApplicationEmail = ?", (c.ApplicationEmail,))
                row = cursor.fetchone()
                if row:
                    candidate_id = row[0]
                    
            # Si introuvable par email, on teste avec le téléphone
            if candidate_id is None and c.ApplicationCandidatePhone1:
                cursor.execute("SELECT TOP 1 CandidateID FROM Candidate WHERE ApplicationCandidatePhone1 = ?", (c.ApplicationCandidatePhone1,))
                row = cursor.fetchone()
                if row:
                    candidate_id = row[0]
                    
            # S'il n'existe pas, on le crée
            if candidate_id is None:
                cursor.execute(
                    "INSERT INTO Candidate (ApplicationEmail, ApplicationCandidateName, ApplicationCandidateBirthDate, ApplicationCandidatePhone1, ApplicationCandidatePhone2, ApplicationCandidateAddress) OUTPUT INSERTED.CandidateID VALUES (?, ?, ?, ?, ?, ?)",
                    (_trunc(c.ApplicationEmail, 50), _trunc(c.ApplicationCandidateName, 50), _trunc(c.ApplicationCandidateBirthDate, 15), _trunc(c.ApplicationCandidatePhone1, 20), _trunc(c.ApplicationCandidatePhone2, 20), _trunc(c.ApplicationCandidateAddress, 50))
                )
                candidate_id = int(cursor.fetchone()[0])
                print(f"[UPDATER] Nouveau candidat inséré : CandidateID={candidate_id}")
            else:
                print(f"[UPDATER] Candidat existant trouvé : CandidateID={candidate_id}")

            cursor.execute(
                "INSERT INTO Application (ApplicationReceiptDate, ApplicationStatus, ApplicationPreselectionScore, ApplicationEvaluationExplanation, ApplicationCandidateID, ApplicationSessionPositionID, status_ai) OUTPUT INSERTED.ApplicationID VALUES (?, 1, ?, ?, ?, ?, 'done')",
                (datetime.now(), round(score, 2), _trunc(explanation, 1000), candidate_id, session_position_id)
            )
            application_id = int(cursor.fetchone()[0])

            if cv_path:
                import os, uuid
                cursor.execute(
                    "INSERT INTO Attachment (AttachmentTitle, AttachmentType, AttachmentReferenceGuid, AttachmentApplicationID) VALUES (?, 'CV', ?, ?)",
                    (_trunc(os.path.basename(cv_path), 100), str(uuid.uuid4()), application_id)
                )

            for skill in ai_data.skills:
                if skill.SkillDescription and skill.SkillDescription.strip():
                    cursor.execute(
                        "INSERT INTO Skill (SkillDescription, SkillApplicationID) VALUES (?, ?)",
                        (_trunc(skill.SkillDescription, 100), application_id)
                    )

            for exp in ai_data.experiences:
                cursor.execute(
                    "INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID) VALUES (?, ?, ?, ?, ?)",
                    (_trunc(exp.ExperienceStartDate, 10), _trunc(exp.ExperienceEndDate, 10), _trunc(exp.ExperienceCompany, 50), _trunc(exp.ExperiencePosition, 50), application_id)
                )

            for deg in ai_data.degrees:
                inst_pk = _resolve_or_create_institution(cursor, deg.institution_id, deg.institution_name, deg.Description)
                sl_pk   = _resolve_or_create_study_level(cursor, deg.study_level_id, deg.study_level_name, deg.Description)
                
                # MAJ Object Python Json
                deg.institution_id = inst_pk
                deg.study_level_id = sl_pk
                
                cursor.execute(
                    "INSERT INTO ApplicationDegree (DegreeObtentionYear, DegreeApplicationID, DegreeInstitutionID, DegreeStudyLevelID, Description) VALUES (?, ?, ?, ?, ?)",
                    (_trunc(deg.DegreeObtentionYear, 4), application_id, inst_pk, sl_pk, _trunc(deg.Description, 100))
                )

            print(f"[UPDATER] Nouveau candidat : ApplicationID={application_id}")
            return application_id
    except Exception as e:
        print(f"[UPDATER] Erreur INSERT : {e}")
        return f"Erreur SQL: {str(e)}"


async def insert_new_candidate_and_application(ai_data, score, explanation, session_position_id, cv_path):
    return await asyncio.to_thread(_sync_insert_new_candidate_and_application, ai_data, score, explanation, session_position_id, cv_path)


def _trunc(value, max_len):
    if value is None:
        return None
    return str(value)[:max_len]