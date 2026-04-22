from pydantic import BaseModel, Field
from typing import List, Optional

# Aligned with the exact Database Schema Models

class Skill(BaseModel):
    SkillDescription: str

class Experience(BaseModel):
    ExperienceStartDate: str
    ExperienceEndDate: Optional[str] = None
    ExperienceCompany: Optional[str] = None
    ExperiencePosition: Optional[str] = None


# Associations and new DB models
class Institution(BaseModel):
    InstitutionAcronym: Optional[str] = None
    InstitutionLabel: str
    InstitutionRank: Optional[int] = None
    InstitutionStatus: Optional[int] = 1

class StudyLevel(BaseModel):
    StudyLevelLabel: str
    StudyLevelRank: Optional[int] = None
    StudyLevelStatus: Optional[int] = 1

class ApplicationDegree(BaseModel):
    DegreeObtentionYear: Optional[str] = None
    DegreeInstitution: Optional[Institution] = None
    DegreeStudyLevel: Optional[StudyLevel] = None
    Description: Optional[str] = None

class Candidate(BaseModel):
    ApplicationEmail: str

    ApplicationCandidateName: str
    ApplicationCandidateBirthDate: Optional[str] = None
    ApplicationCandidatePhone1: Optional[str] = None
    ApplicationCandidatePhone2: Optional[str] = None
    ApplicationCandidateAddress: Optional[str] = None

class ExtractedApplicationData(BaseModel):
    """Holds all extracted arrays required to fill the tables properly."""
    candidate: Candidate
    skills: List[Skill] = Field(default_factory=list)
    experiences: List[Experience] = Field(default_factory=list)
    degrees: List[ApplicationDegree] = Field(default_factory=list)
    session_position_reference: Optional[str] = None
    session_position_description: Optional[str] = None

class ScoreResult(BaseModel):
    score: float
    level: Optional[str] = None
    missing_skills: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    ApplicationEvaluationExplanation: Optional[str] = None
