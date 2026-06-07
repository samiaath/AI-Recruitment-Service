BEGIN TRANSACTION;
BEGIN TRY

    -- =======================================
    -- TRAITEMENT CANDIDAT #1
    -- =======================================

    DECLARE @CandidateID_0 INT;
    SELECT TOP 1 @CandidateID_0 = CandidateID FROM Candidate WHERE ApplicationEmail = 'rayen.boumnijel@hotmail.com';
    IF @CandidateID_0 IS NULL
    BEGIN
        INSERT INTO Candidate (ApplicationEmail, ApplicationCandidateName, ApplicationCandidateBirthDate, ApplicationCandidatePhone1, ApplicationCandidatePhone2, ApplicationCandidateAddress)
        VALUES ('rayen.boumnijel@hotmail.com', 'Boumnijel Rayen', NULL, '21653791744', NULL, 'Bougatfa 2, Tunis Transatlantique');
        SET @CandidateID_0 = SCOPE_IDENTITY();
    END

    DECLARE @SessionPositionID_0 INT;
    SELECT TOP 1 @SessionPositionID_0 = SessionPositionID FROM SessionPosition WHERE PositionReference = 'DEFAULT001';
    IF @SessionPositionID_0 IS NULL
    BEGIN
        SELECT TOP 1 @SessionPositionID_0 = sp.SessionPositionID FROM SessionPosition sp JOIN Session s ON sp.SessionID = s.SessionID WHERE s.SessionDefault = 1;
    END

    DECLARE @ApplicationID_0 INT = NULL;
    SELECT TOP 1 @ApplicationID_0 = ApplicationID FROM Application WHERE ApplicationCandidateID = @CandidateID_0 AND status_ai = 'pending';
    IF @ApplicationID_0 IS NOT NULL
    BEGIN
        -- UPDATE : La candidature 'pending' existe déjà pour ce candidat
        UPDATE Application 
        SET ApplicationInitialScore = 69.5, ApplicationEvaluationExplanation = 'Points forts : Maîtrise .NET et C# Expérience SQL Server Formation Bac+5 Informatique | Points faibles : COBOL non mentionné Technologies .NET MAUI et Angular hors offre Expérience COBOL absente | Conclusion : Profil technique solide mais hors cible COBOL et .NET pur. Adéquation partielle.', status_ai = 'done' 
        WHERE ApplicationID = @ApplicationID_0;
        -- Nettoyage des anciennes listes pour éviter les doublons lors de la mise à jour
        DELETE FROM ApplicationDegree WHERE ApplicationID = @ApplicationID_0;
        DELETE FROM Experience WHERE ExperienceApplicationID = @ApplicationID_0;
        DELETE FROM Skill WHERE SkillApplicationID = @ApplicationID_0;
    END
    ELSE
    BEGIN
        -- INSERT : Nouvelle candidature
        INSERT INTO Application (ApplicationReceiptDate, ApplicationStatus, ApplicationSessionPositionID, ApplicationInitialScore, ApplicationEvaluationExplanation, ApplicationCandidateID, status_ai)
        VALUES ('2026-06-04 15:11:36', 1, @SessionPositionID_0, 69.5, 'Points forts : Maîtrise .NET et C# Expérience SQL Server Formation Bac+5 Informatique | Points faibles : COBOL non mentionné Technologies .NET MAUI et Angular hors offre Expérience COBOL absente | Conclusion : Profil technique solide mais hors cible COBOL et .NET pur. Adéquation partielle.', @CandidateID_0, 'done');
        SET @ApplicationID_0 = SCOPE_IDENTITY();

        -- Insertion Attachment (Pour gérer le CV Path proprement)
        INSERT INTO Attachment (AttachmentTitle, AttachmentType, AttachmentReferenceGuid, AttachmentApplicationID)
        VALUES ('CV - Boumnijel Rayen.pdf', 'PDF', 'F05056b4-a4a9-9200-adee-0278b255b13f', @ApplicationID_0);
    END

    DECLARE @InstID_0_0 INT = NULL;
    SELECT TOP 1 @InstID_0_0 = InstitutionID FROM Institution WHERE InstitutionLabel LIKE 'Ecole Supérieure Privée d''Ingénierie et de Technologies' OR InstitutionLabel LIKE '%Supérieure%' OR InstitutionAcronym = 'ESPDEDT';
    IF @InstID_0_0 IS NULL
    BEGIN
        INSERT INTO Institution (InstitutionAcronym, InstitutionLabel, InstitutionRank, InstitutionStatus, status_ai)
        VALUES ('ESPDEDT', 'Ecole Supérieure Privée d''Ingénierie et de Technologies', 0, 0, 1);
        SET @InstID_0_0 = SCOPE_IDENTITY();
    END
    DECLARE @LevelID_0_0 INT = NULL;
    SELECT TOP 1 @LevelID_0_0 = StudyLevelID FROM StudyLevel WHERE StudyLevelLabel LIKE 'ingénieur' OR StudyLevelLabel LIKE '%ingénieur%';
    IF @LevelID_0_0 IS NULL
    BEGIN
        INSERT INTO StudyLevel (StudyLevelLabel, StudyLevelScore, StudyLevelStatus, status_ai)
        VALUES ('ingénieur', 0, 0, 1);
        SET @LevelID_0_0 = SCOPE_IDENTITY();
    END
    INSERT INTO ApplicationDegree (ApplicationID, InstitutionID, StudyLevelID, ObtentionYear, DegreeLabel)
    VALUES (@ApplicationID_0, @InstID_0_0, @LevelID_0_0, '2023', 'Diplôme d''ingénieur en informatique');
    DECLARE @InstID_0_1 INT = NULL;
    SELECT TOP 1 @InstID_0_1 = InstitutionID FROM Institution WHERE InstitutionLabel LIKE 'Institut Supérieur de Gestion de Tunis' OR InstitutionLabel LIKE '%Supérieur%' OR InstitutionAcronym = 'ISDGDT';
    IF @InstID_0_1 IS NULL
    BEGIN
        INSERT INTO Institution (InstitutionAcronym, InstitutionLabel, InstitutionRank, InstitutionStatus, status_ai)
        VALUES ('ISDGDT', 'Institut Supérieur de Gestion de Tunis', 0, 0, 1);
        SET @InstID_0_1 = SCOPE_IDENTITY();
    END
    DECLARE @LevelID_0_1 INT = NULL;
    SELECT TOP 1 @LevelID_0_1 = StudyLevelID FROM StudyLevel WHERE StudyLevelLabel LIKE 'licence' OR StudyLevelLabel LIKE '%licence%';
    IF @LevelID_0_1 IS NULL
    BEGIN
        INSERT INTO StudyLevel (StudyLevelLabel, StudyLevelScore, StudyLevelStatus, status_ai)
        VALUES ('licence', 0, 0, 1);
        SET @LevelID_0_1 = SCOPE_IDENTITY();
    END
    INSERT INTO ApplicationDegree (ApplicationID, InstitutionID, StudyLevelID, ObtentionYear, DegreeLabel)
    VALUES (@ApplicationID_0, @InstID_0_1, @LevelID_0_1, '2020', 'Licence en informatique de gestion');
    DECLARE @InstID_0_2 INT = NULL;
    SELECT TOP 1 @InstID_0_2 = InstitutionID FROM Institution WHERE InstitutionLabel LIKE 'Lycée Ezzahrouni' OR InstitutionLabel LIKE '%Lycée%' OR InstitutionAcronym = 'LE';
    IF @InstID_0_2 IS NULL
    BEGIN
        INSERT INTO Institution (InstitutionAcronym, InstitutionLabel, InstitutionRank, InstitutionStatus, status_ai)
        VALUES ('LE', 'Lycée Ezzahrouni', 0, 0, 1);
        SET @InstID_0_2 = SCOPE_IDENTITY();
    END
    DECLARE @LevelID_0_2 INT = NULL;
    SELECT TOP 1 @LevelID_0_2 = StudyLevelID FROM StudyLevel WHERE StudyLevelLabel LIKE 'Baccalauréat' OR StudyLevelLabel LIKE '%Baccalauréat%';
    IF @LevelID_0_2 IS NULL
    BEGIN
        INSERT INTO StudyLevel (StudyLevelLabel, StudyLevelScore, StudyLevelStatus, status_ai)
        VALUES ('Baccalauréat', 0, 0, 1);
        SET @LevelID_0_2 = SCOPE_IDENTITY();
    END
    INSERT INTO ApplicationDegree (ApplicationID, InstitutionID, StudyLevelID, ObtentionYear, DegreeLabel)
    VALUES (@ApplicationID_0, @InstID_0_2, @LevelID_0_2, '2020', 'Baccalauréat en informatique');

    INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID)
    VALUES ('2023-08', 'present', 'International Information Developments', 'Analyste développeur', @ApplicationID_0);
    INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID)
    VALUES ('2023-05', '2023-08', 'International Information Developments', 'Stagiaire PFE', @ApplicationID_0);
    INSERT INTO Experience (ExperienceStartDate, ExperienceEndDate, ExperienceCompany, ExperiencePosition, ExperienceApplicationID)
    VALUES ('2021-03', '2021-05', 'One Gate Africa', 'Stagiaire', @ApplicationID_0);

    INSERT INTO Skill (SkillDescription, SkillApplicationID)
    VALUES ('Langages de programmation : .NET, C#', @ApplicationID_0);
    INSERT INTO Skill (SkillDescription, SkillApplicationID)
    VALUES ('Frameworks : Angular, .NET MAUI, SpringBoot', @ApplicationID_0);
    INSERT INTO Skill (SkillDescription, SkillApplicationID)
    VALUES ('Bases de données : SQL Server 2021', @ApplicationID_0);
    INSERT INTO Skill (SkillDescription, SkillApplicationID)
    VALUES ('Outils : Git, WordPress', @ApplicationID_0);
    INSERT INTO Skill (SkillDescription, SkillApplicationID)
    VALUES ('Soft Skills : Gestion de projets, Analyse fonctionnelle', @ApplicationID_0);

    COMMIT TRANSACTION;
    PRINT 'Script inséré avec succès.';
END TRY
BEGIN CATCH
    ROLLBACK TRANSACTION;
    PRINT 'Erreur rencontrée :';
    PRINT ERROR_MESSAGE();
END CATCH;