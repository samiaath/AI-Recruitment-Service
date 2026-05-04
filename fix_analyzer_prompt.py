import pathlib
import re

analyzer_path = pathlib.Path(r'c:\Users\Lenovo\Desktop\Python\ai_service\ai\analyzer.py')
content = analyzer_path.read_text('utf-8')

# Update Prompt to include job description
new_rules = '''── RÈGLE 4 : ANNÉES D'EXPÉRIENCE PERTINENTES (SÉLÉCTIVES) ──
L'OFFRE D'EMPLOI EST : {job_description}
Tu ne dois compter QUE les expériences utiles et liées aux compétences de cette offre.
"total_years_experience" = Somme (en années, ex: 1.5) des expériences (pro + stage + freelance + bénévolat) QUI CORRESPONDENT AU POSTE.
"professional_years_only" = Somme (en années) des expériences pro et freelance QUI CORRESPONDENT AU POSTE.
Si une expérience (ex: bénévolat, stage) n'a rien à voir avec l'offre (ex: offre .NET, mais stage en marketing), sa durée = 0 dans le calcul. ATTENTION : si la personne est née en 2002, sois réaliste sur le cumul.
'''

content = re.sub(r'── RÈGLE 4 : ANNÉES D\'EXPÉRIENCE ──.*?ATTENTION : si la personne est nee en 2002, l\'experience totale ne peut pas raisonnablement exceder qqs annees\. SOIS REALISTE\. Calculez les mois réels\.', new_rules, content, flags=re.DOTALL)

# Update formatting
content = content.replace('prompt = _PROMPT.format(inst_str=inst_str, sl_str=sl_str, cv_text=clean_text)', 'prompt = _PROMPT.format(inst_str=inst_str, sl_str=sl_str, cv_text=clean_text, job_description=position_desc)')

analyzer_path.write_text(content, 'utf-8')
