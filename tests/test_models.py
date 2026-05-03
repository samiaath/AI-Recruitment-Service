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
    
    extracted_data = ExtractedApplicationData(
        candidate=candidate,
        skills=[skill]
    )
    
    assert extracted_data.candidate.ApplicationCandidateName == "Alice"
    assert len(extracted_data.skills) == 1
    assert extracted_data.skills[0].SkillDescription == "Machine Learning"
    assert extracted_data.experiences == []  # default_factory check

def test_score_result_model():
    score_res = ScoreResult(
        score=85.5,
        summary="Good candidate"
    )
    assert score_res.score == 85.5
    assert score_res.summary == "Good candidate"
    assert score_res.level is None
