import json
from datetime import datetime

def generate_sql_scripts_from_json(json_filepath: str, sql_filepath: str):
    """
    Lit le fichier JSON généré par le pipeline d'extraction, 
    et produit un script SQL dynamique. Ce script ne compte PAS sur 
    des IDs statiques, mais utilise DECLARE, SCOPE_IDENTITY() et des 
    sous-requêtes sur la Référence métier (ex: RF001) pour l'insertion.
    """
    
    try:
        with open(json_filepath, "r", encoding="utf-8") as f:
            data_list = json.load(f)
    except FileNotFoundError:
        print(f"Fichier non trouvé : {json_filepath}")
        return
    except json.JSONDecodeError:
        print("Erreur de format JSON.")
        return

    sql_statements = []
    
    sql_statements.append("BEGIN TRANSACTION;")
    sql_statements.append("BEGIN TRY\n")

    for idx, record in enumerate(data_list):
        ai_data = record["ai_extracted_data"]
        candidate = ai_data["candidate"]
        target_ref = record["target_reference"]

        # Échappement basique des quotes SQL (')
        def escape_sql(val):
            if val is None:
                return "NULL"
            return "'" + str(val).replace("'", "''") + "'"

        sql_statements.append(f"    -- =======================================")
        sql_statements.append(f"    -- TRAITEMENT CANDIDAT #{idx + 1}")
        sql_statements.append(f"    -- =======================================\n")

        # 1. Insertion ou Récupération du Candidate
        sql_statements.append(f"    DECLARE @CandidateID_{idx} INT;")
        c_email = escape_sql(candidate.get('ApplicationEmail'))
        c_name = escape_sql(candidate.get('ApplicationCandidateName'))
        
        raw_dob = candidate.get('ApplicationCandidateBirthDate')
        if raw_dob:
            raw_dob = raw_dob.replace("-", "")
        c_dob = escape_sql(raw_dob)
        
        c_p1 = escape_sql(candidate.get('ApplicationCandidatePhone1'))
        c_p2 = escape_sql(candidate.get('ApplicationCandidatePhone2'))
        c_add = escape_sql(candidate.get('ApplicationCandidateAddress'))

        # Vérification si le candidat existe déjà via son email
        sql_statements.append(f"    SELECT TOP 1 @CandidateID_{idx} = CandidateID FROM Candidate WHERE ApplicationEmail = {c_email};")
        sql_statements.append(f"    IF @CandidateID_{idx} IS NULL")
        sql_statements.append(f"    BEGIN")
        sql_statements.append(f"        INSERT INTO Candidate (ApplicationEmail, ApplicationCandidateName, ApplicationCandidateBirthDate, ApplicationCandidatePhone1, ApplicationCandidatePhone2, ApplicationCandidateAddress)")
        sql_statements.append(f"        VALUES ({c_email}, {c_name}, {c_dob}, {c_p1}, {c_p2}, {c_add});")
        sql_statements.append(f"        SET @CandidateID_{idx} = SCOPE_IDENTITY();")
        sql_statements.append(f"    END\n")

        # 2. Identification de la FK de SessionPosition par sa Référence
        sql_statements.append(f"    DECLARE @SessionPositionID_{idx} INT;")
        sql_statements.append(f"    SELECT TOP 1 @SessionPositionID_{idx} = SessionPositionID "
                              f"FROM SessionPosition WHERE PositionReference = {escape_sql(target_ref)};")
        
        # Si la référence n'existe pas dans le nouveau client, on peut forcer une session par défaut
        sql_statements.append(f"    IF @SessionPositionID_{idx} IS NULL")
        sql_statements.append(f"    BEGIN")
        sql_statements.append(f"        SELECT TOP 1 @SessionPositionID_{idx} = sp.SessionPositionID "
                              f"FROM SessionPosition sp "
                              f"JOIN Session s ON sp.SessionID = s.SessionID WHERE s.SessionDefault = 1;")
        sql_statements.append(f"    END\n")

        # 3. Insertion ou Mise à jour Application (Reliée au Candidate)
        status_app = 1  
        
        # Récupération de la date de réception du mail
        meta_origin = record.get("metadata_origin", {})
        received_date_str = meta_origin.get("date_received")
        if received_date_str:
            dt_now = escape_sql(received_date_str)
        else:
            dt_now = escape_sql(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
        score = record.get("score", 0)
        reason = escape_sql(record.get("explanation", "Pas de justification fournie"))
        cv_path_val = record["cv_filename"] or "cv.pdf"

        sql_statements.append(f"    DECLARE @ApplicationID_{idx} INT = NULL;")
        sql_statements.append(f"    SELECT TOP 1 @ApplicationID_{idx} = ApplicationID FROM Application WHERE ApplicationCandidateID = @CandidateID_{idx} AND status_ai = 'pending';")
        
        sql_statements.append(f"    IF @ApplicationID_{idx} IS NOT NULL")
        sql_statements.append(f"    BEGIN")
        sql_statements.append(f"        -- UPDATE : La candidature 'pending' existe déjà pour ce candidat")
        sql_statements.append(f"        UPDATE Application ")
        sql_statements.append(f"        SET ApplicationInitialScore = {score}, ApplicationEvaluationExplanation = {reason}, status_ai = 'done' ")
        sql_statements.append(f"        WHERE ApplicationID = @ApplicationID_{idx};")
        sql_statements.append(f"        -- Nettoyage des anciennes listes pour éviter les doublons lors de la mise à jour")
        sql_statements.append(f"        DELETE FROM ApplicationDegree WHERE ApplicationID = @ApplicationID_{idx};")
        sql_statements.append(f"        DELETE FROM Experience WHERE ExperienceApplicationID = @ApplicationID_{idx};")
        sql_statements.append(f"        DELETE FROM Skill WHERE SkillApplicationID = @ApplicationID_{idx};")
        sql_statements.append(f"    END")
        sql_statements.append(f"    ELSE")
        sql_statements.append(f"    BEGIN")
        sql_statements.append(f"        -- INSERT : Nouvelle candidature")
        sql_statements.append(f"        INSERT INTO Application (ApplicationReceiptDate, ApplicationStatus, ApplicationSessionPositionID, ApplicationInitialScore, ApplicationEvaluationExplanation, ApplicationCandidateID, status_ai)")
        sql_statements.append(f"        VALUES ({dt_now}, {status_app}, @SessionPositionID_{idx}, {score}, {reason}, @CandidateID_{idx}, 'done');")
        sql_statements.append(f"        SET @ApplicationID_{idx} = SCOPE_IDENTITY();\n")
        
        attachment_type = "Word" if cv_path_val.lower().endswith(('.doc', '.docx')) else "PDF"
        
        sql_statements.append(f"        -- Insertion Attachment (Pour gérer le CV Path proprement)")
        sql_statements.append(f"        INSERT INTO Attachment (AttachmentTitle, AttachmentType, AttachmentReferenceGuid, AttachmentApplicationID)")
        sql_statements.append(f"        VALUES ({escape_sql(cv_path_val)}, '{attachment_type}', 'F05056b4-a4a9-9200-adee-0278b255b13f', @ApplicationID_{idx});")
        sql_statements.append(f"    END\n")

        # 4. Diplômes (ApplicationDegree)
        if ai_data.get("degrees"):
            for deg_idx, deg in enumerate(ai_data["degrees"]):
                lbl = escape_sql(deg.get("DegreeLabel", deg.get("DegreeName", "Diplôme ou Formation")))
                year = escape_sql(deg.get("DegreeObtentionYear"))
                
                inst_id = deg.get("institution_id")
                inst_name = escape_sql(deg.get("institution_name") or "Institution Inconnue")
                inst_acronym = escape_sql("".join([c[0] for c in (deg.get("institution_name") or "UNK").split() if c]).upper()[:10][:10])

                study_level_id = deg.get("study_level_id")
                study_level_name = escape_sql(deg.get("study_level_name") or "Niveau Inconnu")

                # On ignore volontairement les IDs (inst_id, study_level_id) locaux car
                # ils ne correspondent pas à la base cible. Résolution exclusive par le Label !
                inst_var = f"@InstID_{idx}_{deg_idx}"
                level_var = f"@LevelID_{idx}_{deg_idx}"
                
                # Extraction d'un mot-clé "fort" (le premier mot significatif de plus de 4 lettres)
                import re
                inst_words = [w for w in re.findall(r'\b\w{4,}\b', inst_name.strip("'")) if w.lower() not in ('ecole', 'institut', 'faculté', 'nationale', 'superieur', 'superieure', 'sciences', 'etudes', 'universite')]
                inst_keyword = f"'%{inst_words[0]}%'" if inst_words else inst_name
                
                # Niveaux : mot-clé
                lvl_words = [w for w in re.findall(r'\b\w{3,}\b', study_level_name.strip("'")) if w.lower() not in ('diplome', 'titre', 'niveau', 'cycle', 'etude')]
                lvl_keyword = f"'%{lvl_words[0]}%'" if lvl_words else study_level_name

                sql_statements.append(f"    DECLARE {inst_var} INT = NULL;")
                sql_statements.append(f"    SELECT TOP 1 {inst_var} = InstitutionID FROM Institution WHERE InstitutionLabel LIKE {inst_name} OR InstitutionLabel LIKE {inst_keyword} OR InstitutionAcronym = {inst_acronym};")
                sql_statements.append(f"    IF {inst_var} IS NULL")
                sql_statements.append(f"    BEGIN")
                sql_statements.append(f"        INSERT INTO Institution (InstitutionAcronym, InstitutionLabel, InstitutionRank, InstitutionStatus, status_ai)")
                sql_statements.append(f"        VALUES ({inst_acronym}, {inst_name}, 0, 0, 1);")
                sql_statements.append(f"        SET {inst_var} = SCOPE_IDENTITY();")
                sql_statements.append(f"    END")

                sql_statements.append(f"    DECLARE {level_var} INT = NULL;")
                sql_statements.append(f"    SELECT TOP 1 {level_var} = StudyLevelID FROM StudyLevel WHERE StudyLevelLabel LIKE {study_level_name} OR StudyLevelLabel LIKE {lvl_keyword};")
                sql_statements.append(f"    IF {level_var} IS NULL")
                sql_statements.append(f"    BEGIN")
                sql_statements.append(f"        INSERT INTO StudyLevel (StudyLevelLabel, StudyLevelScore, StudyLevelStatus, status_ai)")
                sql_statements.append(f"        VALUES ({study_level_name}, 0, 0, 1);")
                sql_statements.append(f"        SET {level_var} = SCOPE_IDENTITY();")
                sql_statements.append(f"    END")

                # On insère avec les variables T-SQL dynamiques
                sql_statements.append(f"    INSERT INTO ApplicationDegree (ApplicationID, InstitutionID, StudyLevelID, ObtentionYear, DegreeLabel)")
                sql_statements.append(f"    VALUES (@ApplicationID_{idx}, {inst_var}, {level_var}, {year}, {lbl});")
            sql_statements.append("")

        # 5. Expériences (Experience)
        if ai_data.get("experiences"):
            for exp_idx, exp in enumerate(ai_data["experiences"]):
                cmp = escape_sql(exp.get("Company", exp.get("ExperienceCompany")))
                rol = escape_sql(exp.get("Role", exp.get("ExperiencePosition")))
                start = escape_sql(exp.get("ExperienceStartDate"))
                end = escape_sql(exp.get("ExperienceEndDate"))
                
                sql_statements.append(f"    INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID)")
                sql_statements.append(f"    VALUES ({start}, {end}, {cmp}, {rol}, @ApplicationID_{idx});")
            sql_statements.append("")

        # 6. Compétences (Skill)
        if ai_data.get("skills"):
            for sk_idx, sk in enumerate(ai_data["skills"]):
                # Gestion du nouveau format groupé (SkillGroup)
                if "category_name" in sk and "skills" in sk:
                    cat = sk.get("category_name", "Compétences")
                    s_list = sk.get("skills", [])
                    label = f"{cat} : {', '.join(s_list)}"
                else:
                    label = sk.get("SkillDescription", sk.get("SkillName", "Autre"))
                    
                s_lbl = escape_sql(label[:300]) # Tronquer pour la base si nécessaire
                
                sql_statements.append(f"    INSERT INTO Skill (SkillDescription, SkillApplicationID)")
                sql_statements.append(f"    VALUES ({s_lbl}, @ApplicationID_{idx});")
            sql_statements.append("")
            
    sql_statements.append("    COMMIT TRANSACTION;")
    sql_statements.append("    PRINT 'Script inséré avec succès.';")
    sql_statements.append("END TRY")
    sql_statements.append("BEGIN CATCH")
    sql_statements.append("    ROLLBACK TRANSACTION;")
    sql_statements.append("    PRINT 'Erreur rencontrée :';")
    sql_statements.append("    PRINT ERROR_MESSAGE();")
    sql_statements.append("END CATCH;")

    # Write the SQL statements to the file
    with open(sql_filepath, "w", encoding="utf-8") as sql_file:
        sql_file.write("\n".join(sql_statements))
        
    print(f"-> Génération SQL terminée : {sql_filepath}")

if __name__ == "__main__":
    import sys
    import os
    
    print("======================================================")
    print(" Génération SQL depuis les résultats d'extraction IA")
    print("======================================================")
    print("1. Générer SQL depuis les EMAILS (pipeline_json_results.json)")
    print("2. Générer SQL depuis la BD / Recommandations (pipeline_db_results.json)")
    print("0. Quitter")
    print("------------------------------------------------------")
    
    choice = input("Veuillez choisir la source (0, 1 ou 2) : ").strip()
    
    # Résolution des chemins dans le dossier courant (Demo/)
    current_dir = os.path.dirname(__file__)
    email_json = os.path.join(current_dir, "pipeline_json_results.json")
    db_json = os.path.join(current_dir, "pipeline_db_results.json")
    output_sql = os.path.join(current_dir, "DYNAMIC_IMPORT_SCRIPT.sql")

    if choice == "1":
        print(f"\n[EXECUTION] Génération SQL pour les dossiers EMAILS...")
        generate_sql_scripts_from_json(email_json, output_sql)
        
    elif choice == "2":
        print(f"\n[EXECUTION] Génération SQL pour la BASE DE DONNÉES / Recommandations...")
        generate_sql_scripts_from_json(db_json, output_sql)
        
    elif choice == "0":
        print("Fermeture du script.")
        sys.exit(0)
    else:
        print("Choix invalide.")
        
    print("Ce fichier .sql peut maintenant être exécuté sur n'importe quel autre serveur de DB sans crasher les clés étangères !")
