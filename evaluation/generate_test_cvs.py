from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import os

test_cvs_dir = os.path.join(os.path.dirname(__file__), "test_cvs")
os.makedirs(test_cvs_dir, exist_ok=True)
styles = getSampleStyleSheet()

def create_cv(filename, content_lines):
    doc = SimpleDocTemplate(os.path.join(test_cvs_dir, filename))
    elements = []
    for line in content_lines:
        elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 10))
    doc.build(elements)


# ===============================
# CV 13 - Profil International (+1)
# ===============================
create_cv("cv_james_okonkwo.pdf", [
    "James Okonkwo",
    "Email: james.okonkwo@techcorp.ca",
    "Phone: +1 416 555 7890",
    "Location: Toronto, Canada",

    "Full Stack Engineer",

    "Skills:",
    "TypeScript, React, Node.js, GraphQL, PostgreSQL, AWS, Docker, Jest",

    "Experience:",
    "2022-Present  Senior Full Stack Engineer - FinTech Global Inc (Toronto)",
    "2019-2022     Full Stack Developer - SaaS Platform Co (Montreal)",
    "2017-2019     Junior Developer - Web Agency (Lagos)",

    "Education:",
    "Bachelor of Computer Science - University of Lagos - 2017",
    "AWS Certified Solutions Architect - 2021",
])

# ===============================
# CV 14 - Changements fréquents (6+ postes en 5 ans)
# ===============================
create_cv("cv_rania_chaabane.pdf", [
    "Rania Chaabane",
    "rania.chaabane@dev.tn",
    "Tél: +216 92 111 222",

    "Développeuse Full Stack",

    "Compétences:",
    "Vue.js, React, Laravel, PHP, MySQL, Git, Docker",

    "Expérience:",
    "2024 (6 mois)  Dev Frontend - Agence Pixel (Tunis)",
    "2023 (4 mois)  Dev Full Stack - Startup Edtech",
    "2023 (5 mois)  Dev Vue.js - SaaS Company",
    "2022 (6 mois)  Dev Laravel - Consulting IT",
    "2022 (4 mois)  Dev PHP - Agence Web Creativ",
    "2021 (7 mois)  Dev Junior - Tech Solutions Tunis",

    "Formation:",
    "Licence Informatique Appliquée - ISSAT Sousse - 2021",
])

# ===============================
# CV 15 - Freelance pur (5+ clients)
# ===============================
create_cv("cv_mehdi_gharbi.pdf", [
    "Mehdi Gharbi",
    "Email: mehdi.gharbi@freelance.dev",
    "Tel: +216 55 321 654",

    "Développeur Freelance Full Stack",

    "Compétences:",
    "Python, Django, React, PostgreSQL, Redis, Docker, REST API, Stripe API",

    "Missions Freelance (2019 - présent):",
    "2023-2024  Plateforme e-commerce - Client: RetailShop Maroc",
    "2022-2023  API Backend Python - Client: HealthTech Startup (Paris)",
    "2021-2022  Dashboard Analytics - Client: LogiCorp Tunisia",
    "2020-2021  Système de réservation - Client: HotelGroup SA",
    "2019-2020  Site institutionnel + CMS - Client: ONG Solidarité",

    "Formation:",
    "Diplôme National d'Ingénieur en Informatique - ENSI - 2019",
])

# ===============================
# CV 16 - Profil technique + management
# ===============================
create_cv("cv_sarra_khelifi.pdf", [
    "Sarra Khelifi",
    "sarra.khelifi@tech-lead.io",
    "Téléphone: +216 71 445 566",

    "Tech Lead & Engineering Manager",

    "Compétences Techniques:",
    "Java, Spring Boot, Microservices, Kubernetes, Kafka, MongoDB",
    "Compétences Management:",
    "Leadership, Recrutement technique, Code Review, Agile/Scrum, OKR",

    "Expérience:",
    "2021-présent  Engineering Manager - Fintech Corp (Tunis)",
    "               Encadrement d'une équipe de 8 développeurs",
    "               Définition de l'architecture technique",
    "2017-2021     Tech Lead Backend - Telecom Solutions SA",
    "2014-2017     Développeur Senior Java - ERP Publisher",

    "Formation:",
    "Ingénieur en Génie Logiciel - ESPRIT - 2014",
])

# ===============================
# CV 17 - Certifications multiples (AWS, PMP, etc.)
# ===============================
create_cv("cv_nizar_hamdi.pdf", [
    "Nizar Hamdi",
    "nizar.hamdi@certified.cloud",
    "Tel: +216 98 776 543",

    "Cloud & DevOps Engineer",

    "Certifications:",
    "AWS Certified Solutions Architect Professional (2023)",
    "AWS Certified DevOps Engineer (2022)",
    "HashiCorp Terraform Associate (2022)",
    "Certified Kubernetes Administrator - CKA (2021)",
    "PMP - Project Management Professional (2020)",

    "Compétences:",
    "AWS, Terraform, Kubernetes, Docker, Jenkins, Ansible, Python, Bash",

    "Expérience:",
    "2020-présent  Cloud Architect - Digital Services Corp",
    "2016-2020     DevOps Engineer - Telecom Tunisia",
    "2013-2016     Administrateur Systèmes Linux - DataCenter Pro",

    "Formation:",
    "Mastère Professionnel Réseaux & Systèmes - FST - 2013",
])

# ===============================
# CV 18 - Profil académique avancé (chercheur / post-doc)
# ===============================
create_cv("cv_dr_leila_ben_fredj.pdf", [
    "Dr. Leila Ben Fredj",
    "leila.benfredj@research.tn",
    "Tel: +216 73 654 321",

    "Research Scientist / NLP Engineer",

    "Skills:",
    "Python, PyTorch, Transformers (HuggingFace), NLP, BERT, LLM fine-tuning,",
    "TensorFlow, Scikit-learn, Research methodology, Academic writing",

    "Academic & Professional Experience:",
    "2023-present  Post-Doctoral Researcher - LORIA Lab (Nancy, France)",
    "               Research on Multilingual LLMs for low-resource languages",
    "2020-2023     PhD Research Assistant - INRIA Sophia-Antipolis",
    "2019 (6mo)    NLP Research Intern - Hugging Face (Paris)",

    "Education:",
    "Doctorat en Traitement Automatique du Langage - Université Côte d'Azur - 2023",
    "Master Recherche Intelligence Artificielle - ENSI Tunis - 2019",
    "Licence Informatique - FST Tunis - 2017",

    "Publications: 4 articles publiés (ACL, EMNLP, COLING)",
])

# ===============================
# CV 19 - Profil non-IT (comptable)
# ===============================
create_cv("cv_walid_mejri.pdf", [
    "Walid Mejri",
    "walid.mejri@compta.tn",
    "Tél: +216 55 198 732",

    "Expert Comptable",

    "Compétences:",
    "Comptabilité générale, Fiscalité, Audit, Sage 100, Excel avancé,",
    "Déclarations TVA, Bilan comptable, Contrôle de gestion",

    "Expérience:",
    "2018-présent  Expert Comptable - Cabinet Mejri & Associés",
    "2014-2018     Comptable Senior - Groupe Industriel BTA",
    "2012-2014     Comptable - PME Import/Export",

    "Formation:",
    "Diplôme d'Expert Comptable - OECT - 2018",
    "Mastère Comptabilité Contrôle Audit - FSEG Sfax - 2012",
])

# ===============================
# CV 20 - CV minimal (1 page, 1 expérience)
# ===============================
create_cv("cv_adam_slimane.pdf", [
    "Adam Slimane",
    "adam.slimane@mail.com",
    "Tel: +216 56 000 111",

    "Développeur Python Junior",

    "Skills: Python, Flask, SQL, Git",

    "Experience:",
    "Stage PFE - Dev Python - DataTech (2024, 6 mois)",

    "Education:",
    "Licence Informatique - ISI - 2024",
])

# ===============================
# CV 21 - Format Europass dense
# ===============================
create_cv("cv_elena_popescu.pdf", [
    "CURRICULUM VITAE - FORMAT EUROPASS",
    "Elena Popescu",
    "elena.popescu@eu.dev",
    "Telephone: +40 721 456 789",
    "Nationality: Romanian | Date of birth: 15/03/1990",

    "PROFESSIONAL EXPERIENCE",
    "01/2020 - Present | Senior Java Developer | TechEU Solutions (Bucharest)",
    "  - Developed microservices architecture using Spring Boot",
    "  - Led migration from monolith to cloud-native on AWS",
    "03/2016 - 12/2019 | Java Developer | Banking Software SRL",
    "  - Core banking system development (SWIFT, ISO20022)",
    "06/2014 - 02/2016 | Junior Developer | Web Factory Romania",

    "EDUCATION AND TRAINING",
    "2014 | Bachelor of Engineering - Computer Science | Politehnica Bucharest",
    "2021 | Oracle Certified Professional Java SE 11",
    "2022 | Spring Professional Certification",

    "TECHNICAL SKILLS",
    "Java, Spring Boot, Microservices, AWS, Docker, Kubernetes, Oracle DB, REST, SOAP",

    "LANGUAGE SKILLS",
    "Romanian (Native), English (C1), French (B2)",
])

# ===============================
# CV 22 - Bilingue FR/EN mélangé
# ===============================
create_cv("cv_bilel_triki.pdf", [
    "Bilel Triki",
    "bilel.triki@bilingual.io",
    "Phone / Tél: +216 97 654 321",

    "Data Engineer / Ingénieur Données",

    "Technical Skills / Compétences Techniques:",
    "Apache Spark, Kafka, Airflow, dbt, Snowflake, BigQuery",
    "Python, SQL, Scala, Bash",
    "AWS S3, Glue, Redshift | Azure Data Factory",

    "Experience / Expérience:",
    "2022-present   Data Engineer - International Fintech (Remote / Paris)",
    "               Built real-time pipelines processing 10M+ events/day",
    "2020-2022      Ingénieur Données - Banque Nationale Tunisienne",
    "               Migration du datawarehouse Oracle vers Snowflake",
    "2019 (Stage)   Data Analyst Intern - Capgemini Tunisia",

    "Formation / Education:",
    "Ingénieur en Informatique - INSAT Tunis - 2020",
    "Certified dbt Developer - 2023",
])

# ===============================
# CV 23 - Stagiaire / alternant fin d'études
# ===============================
create_cv("cv_yasmine_oueslati.pdf", [
    "Yasmine Oueslati",
    "yasmine.oueslati@student.tn",
    "Tél: +216 53 876 543",

    "Étudiante Ingénieure en Alternance - Cybersécurité",

    "Compétences:",
    "Python, Bash, Linux, Wireshark, Nmap, Metasploit, SIEM (débutant),",
    "Réseaux TCP/IP, Active Directory, CTF challenges",

    "Expérience:",
    "2023-2024  Alternance Cybersécurité - Banque de Tunisie",
    "            Participation aux audits de sécurité internes",
    "            Tests de pénétration réseaux (supervision)",
    "2022 (3mo) Stage Réseaux - Orange Tunisie",

    "Projets Académiques (à titre informatif):",
    "Projet PFE: Système de détection d'intrusion basé sur ML",

    "Formation:",
    "Cycle Ingénieur Cybersécurité (en cours) - SUP'COM Tunis - 2025 (attendu)",
    "Classes Préparatoires Maths-Physique - 2020-2022",
])

# ===============================
# CV 24 - Consultant multi-missions
# ===============================
create_cv("cv_anis_boughanmi.pdf", [
    "Anis Boughanmi",
    "anis.boughanmi@consultant.io",
    "Tél: +216 71 234 567",

    "Consultant IT / Architecte Solutions",

    "Compétences:",
    "Architecture SI, TOGAF, SAP, Salesforce, ServiceNow,",
    "Gestion de projet, AMOA, Conduite du changement, ITIL v4",

    "Missions de Conseil:",
    "2022-présent  Consultant Senior Architecture - Société Générale (Mission Paris)",
    "               Refonte du SI de gestion des risques, coordination 12 équipes",
    "2020-2022     Consultant ERP SAP - BNP Paribas (Mission Tunis)",
    "               Implémentation SAP S/4HANA module Finance",
    "2018-2020     Consultant Salesforce CRM - Telecom Africa Group",
    "2015-2018     Analyste AMOA - Ministère des Finances Tunisie",

    "Formation:",
    "Mastère Systèmes d'Information - HEC Paris Executive - 2015",
    "Ingénieur Informatique - ENIT - 2012",
    "Certification TOGAF 9.2 - 2019",
    "Certification ITIL v4 - 2021",
])

# ===============================
# CV 25 - Senior 20+ ans d'expérience
# ===============================
create_cv("cv_habib_rezgui.pdf", [
    "Habib Rezgui",
    "habib.rezgui@senior-architect.tn",
    "Tél: +216 71 889 900",

    "Directeur Technique / CTO",

    "Compétences:",
    "Architecture distribuée, Java EE, .NET, Oracle, SQL Server,",
    "Cloud AWS/Azure, Microservices, Leadership technique,",
    "Gestion de budget IT, Vision stratégique, Recrutement",

    "Parcours (25 ans):",
    "2018-présent  CTO - Groupe Assurance Tunisie",
    "               Direction d'une équipe de 40 personnes, budget 3M TND/an",
    "               Modernisation complète du SI legacy vers cloud hybride",
    "2012-2018     Directeur des Systèmes d'Information - Banque Zitouna",
    "               Mise en place du core banking system T24 (Temenos)",
    "2007-2012     Architecte Solutions Senior - IBM Tunisia",
    "2003-2007     Chef de Projet Technique - Telnet Holding",
    "2001-2003     Développeur Senior Java - Sopra Tunisia",
    "1999-2001     Développeur - BIAT (Stage + CDD)",

    "Formation:",
    "Ingénieur Informatique - ENSI - 1999",
    "MBA Management & Stratégie - ISG Tunis - 2010",
    "Certification TOGAF 9 - 2014",
])

print("✅ 13 CVs PDF générés (CV_013 à CV_025) dans le dossier test_cvs/")