import json
import random

DATASET_FILE = "evaluation/test_dataset.json"

names = [
    "Sami Ben Mustapha", "Claire Leroy", "Marc Tremblay", "Julie Morel",
    "Antoine Dupont", "Léa Rousseau", "Paul Bernard", "Emma Petit",
    "Lucas Martin", "Chloé Dubois", "Hugo Simon", "Manon Laurent",
    "Arthur Michel", "Camille Garcia", "Théo David", "Inès Richard",
    "Louis Roux", "Sarah Vincent", "Victor Garnier", "Nadia Khelifi",
    "Bastien Faure", "Amina Benali", "Romain Blanc", "Céline Gauthier",
    "Hassan Mansour"
]

companies = [
    "Capgemini", "Sopra Steria", "TechCorp", "Viseo", "Orange Business",
    "Dassault Systèmes", "Ubisoft", "Ledger", "Qonto", "Alan",
    "Doctolib", "Mirakl", "Criteo", "OvhCloud", "Aircall",
    "BlaBlaCar", "PayFit", "Sendinblue", "Shift Technology", "ContentSquare"
]

schools = [
    "Polytechnique", "CentraleSupélec", "Mines ParisTech", "ENSI", "ESPRIT",
    "Sorbonne Université", "Université Paris-Saclay", "EPITA", "Epitech", "INSA Lyon"
]

degrees = [
    "Diplôme d'Ingénieur", "Master en Informatique", "Master Data Science",
    "Licence en Informatique", "Mastère Spécialisé", "Bachelor Web & Mobile"
]

def update_test_cases():
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for i, tc in enumerate(data["test_cases"]):
        # Update only indices 25 to 49 (CV 26 to 50)
        idx = int(tc['id'].split('_')[1])
        if 26 <= idx <= 50:
            name = names[idx - 26]
            email = f"{name.lower().replace(' ', '.')}@example.com"
            phone = f"+33 6 {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}"
            
            c = tc["expected_output"]["candidate"]
            c["ApplicationCandidateName"] = name
            c["ApplicationEmail"] = email
            c["ApplicationCandidatePhone1"] = phone

            # Update experiences
            for i_exp, exp in enumerate(tc["expected_output"].get("experiences", [])):
                exp["ExperienceCompany"] = random.choice(companies)
            
            # Update education degrees
            for i_edu, edu in enumerate(tc["expected_output"].get("degrees", [])):
                deg = random.choice(degrees)
                school = random.choice(schools)
                year = str(random.randint(2010, 2023))
                
                edu["DegreeLabel"] = f"{deg} - {school}"
                edu["DegreeObtentionYear"] = year
                if "Institution" not in edu:
                    edu["Institution"] = school
                    
            # For retro-compatibility with some older setups if needed:
            if "educations" in tc["expected_output"]:
                for edu in tc["expected_output"]["educations"]:
                    deg = random.choice(degrees)
                    school = random.choice(schools)
                    year = str(random.randint(2010, 2023))
                    
                    edu["EducationDegree"] = f"{deg} - {school}"
                    edu["DegreeObtentionYear"] = year
                    if "Institution" not in edu:
                        edu["Institution"] = school

    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
if __name__ == "__main__":
    update_test_cases()
    print("Test dataset JSON updated with realistic data for CVs 26-50.")
