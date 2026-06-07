import json
import glob

latest = max(glob.glob('evaluation/evaluations_results/*.json'))
data = json.load(open(latest, encoding='utf-8'))
errors = []
for r in data['detailed_results']:
    e = r['score_accuracy']['expected']
    a = r['score_accuracy']['actual']
    if e is not None and a is not None:
        errors.append((r['cv_id'], e, a, abs(e-a)))

errors.sort(key=lambda x: x[3], reverse=True)
for r in errors[:20]:
    print(f"{r[0]}: Exp {r[1]:.1f}, Act {r[2]:.1f}, Err {r[3]:.1f}")
print(f"MAE Global: {sum(x[3] for x in errors)/len(errors):.2f}")
