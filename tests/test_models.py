import pytest
from pydantic import ValidationError
from ai_service.models import Candidate, Skill, Experience, StudyLevel, Institution, ApplicationDegree, ExtractedApplicationData, ScoreResult

def test_skill_model():
    skill = Skill(SkillDescription="Python")
    assert skill.SkillDescription == "Python"

def test_candidate_model():
    candidate = Candidate(
        ApplicationEmail="test@example.com",
        ApplicationCandidateName="John Doe",
        ApplicationCandidatePhone1="1234567890"
    )
    assert candidate.ApplicationEmail == "test@example.com"
    assert candidate.ApplicationCandidateName == "John Doe"
    assert candidate.ApplicationCandidatePhone1 == "1234567890"

def test_candidate_model_missing_required():
    with pytest.raises(ValidationError):
        # ApplicationEmail and ApplicationCandidateName are required
        Candidate()

def test_extracted_application_data_model():
    candidate = Candidate(
        ApplicationEmail="test_extracted@example.com",
        ApplicationCandidateName="Alice"
    )
    skill = Skill(SkillDescription="Machine Learning")
    degree = ApplicationDegree(DegreeLabel="Master Data Science")
    
    extracted_data = ExtractedApplicationData(
        candidate=candidate,
        skills=[skill],
        degrees=[degree]
    )
    
    assert extracted_data.candidate.ApplicationCandidateName == "Alice"
    assert len(extracted_data.skills) == 1
    assert extracted_data.skills[0].SkillDescription == "Machine Learning"
    assert len(extracted_data.degrees) == 1
    assert extracted_data.degrees[0].DegreeLabel == "Master Data Science"
    assert extracted_data.experiences == []  # default_factory check

def test_application_degree_model():
    degree = ApplicationDegree(DegreeLabel="Licence Informatique", DegreeObtentionYear="2024")
    assert degree.DegreeLabel == "Licence Informatique"
    assert degree.DegreeObtentionYear == "2024"

def test_application_degree_model_missing_required():
    with pytest.raises(ValidationError):
        # DegreeLabel is required and strictly typed
        ApplicationDegree()

def test_score_result_model():
    score_res = ScoreResult(
        score=85.5,
        summary="Good candidate"
    )
    assert score_res.score == 85.5
    assert score_res.summary == "Good candidate"
    assert score_res.level is None
