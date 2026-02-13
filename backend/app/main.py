from fastapi import FastAPI, Body, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# load backend/.env for local development (ignored by git)
base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

app = FastAPI(title="Recipe Rag Assistant - API")

# enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# initialize DB
from .db import init_db
init_db()

from .auth import get_db, create_user, authenticate_user, create_access_token, get_current_user
from . import models
from sqlalchemy.orm import Session
import json as _json


@app.post('/auth/register')
def register(username: str = Body(...), password: str = Body(...), db: Session = Depends(get_db)):
    existing = db.query(models.User).filter_by(username=username).first()
    if existing:
        raise HTTPException(status_code=400, detail='username taken')
    user = create_user(db, username, password)
    return {'id': user.id, 'username': user.username}


@app.post('/auth/login')
def login(username: str = Body(...), password: str = Body(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=400, detail='invalid credentials')
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get('/user/prefs')
def get_prefs(current_user = Depends(get_current_user)):
    try:
        return _json.loads(current_user.prefs or '{}')
    except Exception:
        return {}


@app.post('/user/prefs')
def set_prefs(prefs: Dict[str, Any] = Body(...), db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    current_user.prefs = _json.dumps(prefs)
    db.add(current_user)
    db.commit()
    return {'status': 'ok'}


class Recipe(BaseModel):
    id: str
    title: str
    ingredients: List[str]
    steps: List[str]


class MealPlanRequest(BaseModel):
    days: int = 7
    calorie_target: Optional[int] = None
    dietary_restrictions: Optional[List[str]] = None


class GroceryRequest(BaseModel):
    recipe_ids: List[str]


def _data_dir() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))


def load_recipes() -> List[Dict[str, Any]]:
    base = _data_dir()
    path = os.path.join(base, 'recipes.json')
    if not os.path.exists(path):
        path = os.path.join(base, 'recipes.sample.json')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_recipe_by_id(rid: str) -> Optional[Dict[str, Any]]:
    for r in load_recipes():
        if str(r.get('id')) == str(rid):
            return r
    return None


_COMPRESSED_INDEX_CACHE: Optional[Dict[str, Any]] = None


def load_compressed_index() -> Dict[str, Any]:
    global _COMPRESSED_INDEX_CACHE
    cache = _COMPRESSED_INDEX_CACHE
    if cache is not None:
        return cache
    base = _data_dir()
    path = os.path.join(base, 'compressed_index.json')
    if not os.path.exists(path):
        path = os.path.join(base, 'compressed_index.json')
    if not os.path.exists(path):
        empty = {'count': 0, 'entries': []}
        _COMPRESSED_INDEX_CACHE = empty
        return empty
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        _COMPRESSED_INDEX_CACHE = data
        return data


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/recipes/sample")
def sample_recipes():
    # prefer `data/recipes.json` if present, otherwise fall back to sample
    base = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    sample_path = os.path.join(base, 'recipes.json')
    if not os.path.exists(sample_path):
        sample_path = os.path.join(base, 'recipes.sample.json')
    sample_path = os.path.normpath(sample_path)
    if os.path.exists(sample_path):
        with open(sample_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"count": len(data), "recipes": data}
    return {"count": 0, "recipes": []}


@app.get("/search")
def search(q: str = ""):
    # Search titles and ingredient text (supports simple CSV-derived samples)
    sample = sample_recipes()["recipes"]
    if not q:
        return sample
    ql = q.lower()
    def matches(r):
        title = (r.get('title') or '')
        if ql in title.lower():
            return True
        # check ingredients: list of strings or dicts
        ings = r.get('ingredients') or []
        for ing in ings:
            if isinstance(ing, str):
                if ql in ing.lower():
                    return True
            elif isinstance(ing, dict):
                name = (ing.get('name') or ing.get('raw') or '')
                if ql in str(name).lower():
                    return True
        # check steps
        steps = r.get('steps') or []
        for s in steps:
            if isinstance(s, str) and ql in s.lower():
                return True
        return False

    return [r for r in sample if matches(r)]


@app.get('/recipe/{recipe_id}')
def recipe_detail(recipe_id: str):
    r = get_recipe_by_id(recipe_id)
    if not r:
        raise HTTPException(status_code=404, detail='recipe not found')
    # attach compression metadata if available
    comp_index = load_compressed_index()
    entry = next((e for e in comp_index.get('entries', []) if e.get('id') == recipe_id), None)
    return {'recipe': r, 'compression': entry}


@app.post('/mealplan')
def mealplan(req: MealPlanRequest = Body(...)):
    recipes = load_recipes()
    if not recipes:
        raise HTTPException(status_code=500, detail='no recipes available')
    # simple filter by exclusion of restriction keywords in ingredients
    def allowed(r):
        if not req.dietary_restrictions:
            return True
        ings = r.get('ingredients', [])
        names = []
        for i in ings:
            if isinstance(i, dict):
                names.append((i.get('name') or '') .lower())
            else:
                names.append(str(i).lower())
        for dr in req.dietary_restrictions:
            if any(dr.lower() in n for n in names):
                return False
        return True

    pool = [r for r in recipes if allowed(r)]
    if not pool:
        raise HTTPException(status_code=400, detail='no recipes match dietary restrictions')

    days = max(1, min(14, int(req.days)))
    plan = []
    # naive round-robin selection of recipes
    idx = 0
    for d in range(days):
        meal = pool[idx % len(pool)]
        plan.append({'day': d + 1, 'recipe_id': meal.get('id'), 'title': meal.get('title')})
        idx += 1
    return {'days': days, 'plan': plan}


@app.post('/grocery')
def grocery(req: GroceryRequest = Body(...)):
    items = {}
    for rid in req.recipe_ids:
        r = get_recipe_by_id(rid)
        if not r:
            continue
        for ing in r.get('ingredients', []):
            if isinstance(ing, dict):
                name = ing.get('name') or ing.get('raw') or ''
                qty = ing.get('quantity')
                unit = ing.get('unit')
                key = str(name).strip().lower()
                if key not in items:
                    items[key] = {'name': name, 'quantity': qty or 0, 'unit': unit}
                else:
                    # sum numeric quantities when possible
                    try:
                        if qty:
                            items[key]['quantity'] = (items[key].get('quantity') or 0) + qty
                    except Exception:
                        pass
            else:
                # raw string, aggregate by raw text
                key = str(ing).strip().lower()
                if key not in items:
                    items[key] = {'name': str(ing), 'quantity': None, 'unit': None}
    return {'grocery': list(items.values())}


@app.get('/compress-status')
def compress_status(limit: Optional[int] = None, ids: Optional[List[str]] = Query(default=None)):
    idx = load_compressed_index()
    total = idx.get('count', 0)
    all_entries = idx.get('entries', [])
    saved_total = sum(
        (e.get('orig_len') or 0) - (e.get('compressed_len') or 0)
        for e in all_entries
        if e.get('orig_len')
    )

    entries = all_entries
    if ids:
        wanted = {str(i) for i in ids}
        entries = [e for e in entries if str(e.get('id')) in wanted]
    elif limit is not None:
        limit = max(0, min(5000, int(limit)))
        entries = entries[:limit]
    return {'count': total, 'entries': entries, 'bytes_saved': saved_total}


@app.get('/compress-status/summary')
def compress_status_summary():
    idx = load_compressed_index()
    entries = idx.get('entries', [])
    saved = sum((e.get('orig_len') or 0) - (e.get('compressed_len') or 0) for e in entries if e.get('orig_len'))
    return {'count': idx.get('count', 0), 'bytes_saved': saved}
