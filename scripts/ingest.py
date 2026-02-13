"""
Sample ingestion script (template).
This reads JSON files in `data/recipes_raw/` and normalizes them to `data/recipes.json`.
"""
import json
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[0] / '..' / 'data' / 'recipes_raw'
OUT_FILE = Path(__file__).resolve().parents[0] / '..' / 'data' / 'recipes.json'


def normalize_recipe(r):
    # Implement normalization: title, ingredients[], steps[], nutrition{}
    return {
        'id': r.get('id') or r.get('url', '')[:32],
        'title': r.get('title', 'Untitled'),
        'ingredients': r.get('ingredients', []),
        'steps': r.get('steps', [])
    }


def run():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    collected = []
    for p in RAW_DIR.glob('*.json'):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for r in data:
                    collected.append(normalize_recipe(r))
            else:
                collected.append(normalize_recipe(data))
        except Exception as e:
            print('skip', p, e)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(collected, f, indent=2)
    print('wrote', OUT_FILE, 'count=', len(collected))

"""Ingestion CLI

Reads JSON recipe files from `data/recipes_raw/`, normalizes fields,
parses ingredient quantities/units, deduplicates, and writes a
canonical `data/recipes.json` suitable for development.

Usage:
  python scripts/ingest.py --raw-dir data/recipes_raw --out data/recipes.json
"""
import argparse
import csv
import json
import re
from pathlib import Path
from fractions import Fraction
from typing import Optional

# common encodings to try when reading large CSVs
TRY_ENCODINGS = ['utf-8', 'utf-8-sig', 'cp1252', 'latin-1', 'utf-16']


def detect_csv_encoding(path: Path):
    """Try common encodings and return the first that parses as CSV with headers."""
    for enc in TRY_ENCODINGS:
        try:
            with path.open('r', encoding=enc, newline='') as f:
                # try to read a few lines
                sample = f.read(4096)
            # try DictReader on sample by reopening file
            with path.open('r', encoding=enc, newline='') as f:
                reader = csv.DictReader(f)
                # must have fieldnames and at least one row to be valid
                fn = reader.fieldnames
                if fn and any(fn):
                    # attempt to read one row
                    try:
                        next(reader)
                    except StopIteration:
                        # empty CSV but encoding worked
                        return enc
                    return enc
        except Exception:
            continue
    return None


def parse_quantity(qstr: str) -> Optional[float]:
    if not qstr:
        return None
    qstr = qstr.strip()
    # handle mixed numbers like '1 1/2'
    try:
        if ' ' in qstr and '/' in qstr:
            whole, frac = qstr.split(' ', 1)
            return float(int(whole) + Fraction(frac))
        if '/' in qstr:
            return float(Fraction(qstr))
        return float(qstr)
    except Exception:
        return None


UNIT_MAP = {
    'tbsp': 'tablespoon', 'tbs': 'tablespoon', 'tablespoons': 'tablespoon', 'tbsp.': 'tablespoon',
    'tsp': 'teaspoon', 'tsps': 'teaspoon', 'teaspoons': 'teaspoon',
    'cup': 'cup', 'cups': 'cup',
    'g': 'gram', 'gram': 'gram', 'grams': 'gram',
    'kg': 'kilogram',
    'oz': 'ounce', 'ounce': 'ounce', 'ounces': 'ounce',
    'lb': 'pound', 'pound': 'pound', 'pounds': 'pound',
    'clove': 'clove', 'cloves': 'clove',
    'slice': 'slice', 'slices': 'slice'
}


def normalize_unit(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.lower().strip().rstrip('.')
    return UNIT_MAP.get(u, u)


ING_RE = re.compile(r"^\s*(?P<qty>\d+(?:[ \t]\d+\/\d+|\/\d+|\.\d+)?)?\s*(?P<unit>[a-zA-Z]+)?\s*(?P<name>.+)$")


def parse_ingredient(ing_raw: str) -> dict:
    m = ING_RE.match(ing_raw)
    if not m:
        return {'raw': ing_raw, 'quantity': None, 'unit': None, 'name': ing_raw.strip()}
    qty = m.group('qty')
    unit = m.group('unit')
    name = m.group('name') or ''
    quantity = parse_quantity(qty) if qty else None
    unit_n = normalize_unit(unit)
    return {'raw': ing_raw, 'quantity': quantity, 'unit': unit_n, 'name': name.strip()}


def split_delimited_field(val: Optional[str]):
    if not val:
        return []
    # common delimiters: ||, ;;, |, ;, \n
    if '||' in val:
        parts = [p.strip() for p in val.split('||') if p.strip()]
    elif '\n' in val:
        parts = [p.strip() for p in val.splitlines() if p.strip()]
    elif ';' in val:
        parts = [p.strip() for p in val.split(';') if p.strip()]
    elif '|' in val:
        parts = [p.strip() for p in val.split('|') if p.strip()]
    else:
        parts = [val.strip()]
    return parts


def parse_csv_cell(val: Optional[str]):
    """Parse a CSV cell that may contain a JSON array or delimited string.
    Returns a list of strings.
    """
    if not val:
        return []
    v = val.strip()
    # try JSON list/array first
    try:
        if v.startswith('[') or v.startswith('{'):
            parsed = json.loads(v)
            if isinstance(parsed, list):
                # ensure all elements are strings
                return [str(p) for p in parsed]
            if isinstance(parsed, dict):
                return [json.dumps(parsed, ensure_ascii=False)]
    except Exception:
        pass
    # fallback to delimiter splitting
    return split_delimited_field(v)


def normalize_recipe(r: dict) -> dict:
    rid = r.get('id') or r.get('url') or (r.get('title') or '')[:64]
    title = r.get('title') or 'Untitled'
    ingredients = r.get('ingredients') or []
    parsed_ings = [parse_ingredient(i) if isinstance(i, str) else i for i in ingredients]
    steps = r.get('steps') or []
    nutrition = r.get('nutrition') or {}
    return {
        'id': str(rid),
        'title': title,
        'ingredients': parsed_ings,
        'steps': steps,
        'nutrition': nutrition,
        'source_url': r.get('url') or r.get('source_url')
    }


def run(raw_dir: Path, out_file: Path, sample_limit: Optional[int] = None):
    raw_dir.mkdir(parents=True, exist_ok=True)
    collected = []
    seen_ids = set()
    for p in sorted(raw_dir.glob('*')):
        try:
            if p.suffix.lower() == '.json':
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else [data]
                for r in items:
                    nr = normalize_recipe(r)
                    if nr['id'] in seen_ids:
                        continue
                    seen_ids.add(nr['id'])
                    collected.append(nr)
                    if sample_limit and len(collected) >= sample_limit:
                        break
            elif p.suffix.lower() == '.csv':
                # detect encoding (tries common encodings)
                enc = detect_csv_encoding(p) or 'utf-8'
                with open(p, 'r', encoding=enc, newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # CSV columns expected: id,title,ingredients,steps,nutrition,source_url
                        # support many header name variants
                        title = row.get('title') or row.get('recipe_title') or row.get('name') or row.get('headline')
                        steps_raw = row.get('steps') or row.get('directions') or row.get('instructions') or row.get('description')
                        item = {
                            'id': row.get('id') or row.get('url') or title,
                            'title': title,
                            'ingredients': parse_csv_cell(row.get('ingredients') or row.get('ingredient') or row.get('ingredients_list')),
                            'steps': parse_csv_cell(steps_raw),
                            'nutrition': row.get('nutrition') or row.get('nutrition_info') or {},
                            'source_url': row.get('source_url') or row.get('url') or row.get('source')
                        }
                        # if steps empty but description exists, use description as a single step
                        if (not item['steps']) and row.get('description'):
                            item['steps'] = [row.get('description')]
                        nr = normalize_recipe(item)
                        if nr['id'] in seen_ids:
                            continue
                        seen_ids.add(nr['id'])
                        collected.append(nr)
                        if sample_limit and len(collected) >= sample_limit:
                            break
            else:
                # skip unknown file types
                continue
            if sample_limit and len(collected) >= sample_limit:
                break
        except Exception as e:
            print('skip', p, e)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)
    print('wrote', out_file, 'count=', len(collected))


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw-dir', default='data/recipes_raw')
    parser.add_argument('--out', default='data/recipes.json')
    parser.add_argument('--sample', type=int, default=0, help='limit number of recipes (0 = all)')
    args = parser.parse_args()
    run(Path(args.raw_dir), Path(args.out), sample_limit=(args.sample or None))


if __name__ == '__main__':
    cli()
