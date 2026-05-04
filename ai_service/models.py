from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class ExperienceType(str, Enum):
    PROFESSIONAL = "professional"
    INTERNSHIP = "internship"
    VOLUNTEERING = "volunteering"
    FREELANCE = "freelance"
    ACADEMIC = "academic"
    UNKNOWN = "unknown"

class ScoreBreakdown(BaseModel):
    skills_match: float = 0.0
    experience_years: float = 0.0
    education_level: float = 0.0
    seniority_match: float = 0.0

class Skill(BaseModel):
    SkillDescription: str

class Experience(BaseModel):
    experience_type: Optional[ExperienceType] = ExperienceType.UNKNOWN
    ExperienceStartDate: Optional[str] = None
    ExperienceEndDate: Optional[str] = None
    ExperienceCompany: Optional[str] = None
    ExperiencePosition: Optional[str] = None
    ExperienceDescription: Optional[str] = Field(default=None, exclude=True)
    duration_months: Optional[float] = None

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
    institution_id: Optional[int] = None
    institution_name: Optional[str] = None
    study_level_id: Optional[int] = None
    study_level_name: Optional[str] = None
    Description: Optional[str] = None

class Candidate(BaseModel):
    ApplicationEmail: str
    ApplicationCandidateName: str
    ApplicationCandidateBirthDate: Optional[str] = None
    ApplicationCandidatePhone1: Optional[str] = None
    ApplicationCandidatePhone2: Optional[str] = None
    ApplicationCandidateAddress: Optional[str] = None

class ExtractedApplicationData(BaseModel):
    candidate: Candidate
    skills: List[Skill] = Field(default_factory=list)
    experiences: List[Experience] = Field(default_factory=list)
    degrees: List[ApplicationDegree] = Field(default_factory=list)
    total_years_experience: Optional[float] = 0.0
    professional_years_only: Optional[float] = 0.0
    session_position_reference: Optional[str] = None
    session_position_description: Optional[str] = None

class ScoreResult(BaseModel):
    score: float
    level: Optional[str] = None
    missing_skills: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    ApplicationEvaluationExplanation: Optional[str] = None
