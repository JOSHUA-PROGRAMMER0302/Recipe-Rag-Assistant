"""Compress recipes using ScaleDown client and write blobs + index.

Outputs:
  data/compressed/<recipe_id>.json  - compressed blob + metadata
  data/compressed_index.json       - mapping and stats
"""
import json
from pathlib import Path
from scripts.scaledown_client import compress_text
import argparse
import re


def build_text_for_recipe(r: dict) -> str:
    parts = []
    parts.append(f"TITLE: {r.get('title','')}")
    ings = r.get('ingredients', [])
    if ings:
        parts.append('\nINGREDIENTS:\n')
        for i in ings:
            if isinstance(i, dict):
                parts.append(i.get('raw') or i.get('name',''))
            else:
                parts.append(str(i))
    steps = r.get('steps', [])
    if steps:
        parts.append('\nSTEPS:\n')
        for s in steps:
            parts.append(str(s))
    nutrition = r.get('nutrition')
    if nutrition:
        parts.append('\nNUTRITION:\n')
        parts.append(json.dumps(nutrition, ensure_ascii=False))
    return '\n'.join(parts)


def run(in_file: Path, out_dir: Path, index_file: Path, sample: int = 0):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(in_file, 'r', encoding='utf-8') as f:
        recipes = json.load(f)
    index = {'count': 0, 'entries': []}
    for i, r in enumerate(recipes):
        if sample and i >= sample:
            break
        rid = r.get('id') or f'recipe_{i}'
        # sanitize id for use as filename
        safe = re.sub(r'[^A-Za-z0-9._-]', '_', str(rid)).strip('_')
        if not safe:
            safe = f'recipe_{i}'
        text = build_text_for_recipe(r)
        resp = compress_text(text)
        # write blob file
        blob_name = f"{i}_{safe}.json"
        blob_path = out_dir / blob_name
        blob_obj = {
            'id': rid,
            'method': resp.get('method'),
            'compressed_blob_b64': resp.get('compressed_blob_b64') or resp.get('meta') or resp.get('data'),
            'orig_len': resp.get('orig_len'),
            'compressed_len': resp.get('compressed_len')
        }
        with open(blob_path, 'w', encoding='utf-8') as bf:
            json.dump(blob_obj, bf, indent=2, ensure_ascii=False)
        index['entries'].append({'id': rid, 'blob': str(blob_path.name), 'method': blob_obj['method'], 'orig_len': blob_obj.get('orig_len'), 'compressed_len': blob_obj.get('compressed_len')})
        index['count'] += 1
    with open(index_file, 'w', encoding='utf-8') as ix:
        json.dump(index, ix, indent=2, ensure_ascii=False)
    print('wrote blobs to', out_dir, 'index=', index_file)


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='infile', default='data/recipes.json')
    parser.add_argument('--out-dir', dest='outdir', default='data/compressed')
    parser.add_argument('--index', dest='index', default='data/compressed_index.json')
    parser.add_argument('--sample', type=int, default=0)
    args = parser.parse_args()
    run(Path(args.infile), Path(args.outdir), Path(args.index), sample=args.sample or 0)


if __name__ == '__main__':
    cli()
