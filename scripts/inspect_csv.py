import csv
from pathlib import Path

p = Path('data/1_Recipe_csv.csv')
print('File exists:', p.exists())
for enc in ('utf-8', 'latin-1'):
    try:
        with p.open('r', encoding=enc, newline='') as f:
            text = f.read()
        lines = text.splitlines()
        print(f"encoding={enc} lines={len(lines)}")
        # try csv reader
        with p.open('r', encoding=enc, newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"encoding={enc} csv_rows={len(rows)}")
        if rows:
            print('First 5 titles:')
            for i,r in enumerate(rows[:5]):
                print(i+1, r.get('recipe_title')[:80])
    except Exception as e:
        print('encoding', enc, 'error', e)
