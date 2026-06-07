import traceback

with open('evaluation/generate_test_cvs.py', 'r', encoding='utf-8') as f:
    original_code = f.read()

append_code = """
import json

# ===============================
# CV 26 à 50 - Génération Dynamique
# ===============================
def generate_last_25_cvs():
    with open(os.path.join(os.path.dirname(__file__), 'test_dataset.json'), 'r', encoding='utf-8') as ds_file:
        dataset = json.load(ds_file)
        
    for tc in dataset['test_cases'][25:]:
        idx = tc['id'].split('_')[1]
        c = tc['expected_output']['candidate']
        lines = [
            c.get('ApplicationCandidateName', ''),
            f"Email: {c.get('ApplicationEmail', '')}",
            f"Tél: {c.get('ApplicationCandidatePhone1', '')}",
            "",
            "Compétences:",
            ", ".join(tc['expected_output'].get('skills', [])),
            "",
            "Expériences professionnelles:"
        ]
        
        for exp in tc['expected_output'].get('experiences', []):
            start = exp.get('ExperienceStartDate', '2020')
            end = exp.get('ExperienceEndDate', 'présent')
            lines.append(f"{start} - {end}  {exp.get('ExperiencePosition', '')} - {exp.get('ExperienceCompany', '')}")
        
        lines.append("")
        lines.append("Formation:")
        
        for deg in tc['expected_output'].get('degrees', []):
            lines.append(deg.get('DegreeLabel', ''))
            
        create_cv(f"cv_{idx}.pdf", lines)
        
generate_last_25_cvs()
print("✅ 25 CVs PDF générés dynamiquement (CV_026 à CV_050) dans le dossier test_cvs/")
"""

if "generate_last_25_cvs" not in original_code:
    with open('evaluation/generate_test_cvs.py', 'a', encoding='utf-8') as f:
        f.write(append_code)
        
print("Updated generate_test_cvs.py")
