# IGCSE 0580/0654 Recap Platform

Classroom-ready revision platform for Cambridge IGCSE 0580 (Mathematics) and 0654 (Coordinated Sciences). Currently serves a single static recap page for 0580; being scaled into a full platform per `.claude/state/plan.md`.

- **Production**: https://igcse.menghi.dev (Railway-hosted Flask app, Cloudflare DNS)
- **Exam date on page**: 29 Apr 2026

## Dev loop

All dev runs against Railway's real env vars + Postgres.

```bash
# 1. Install deps into a local venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2a. Run tests (SQLite in-memory — no Railway needed)
pytest

# 2b. Run the app against Railway env vars + Postgres
railway run python app.py          # → http://localhost:5000
# or, without railway-cli, copy .env.example → .env and `python app.py`
```

The old "double-click `index.html`" flow no longer works — the page is now a Jinja template rendered by Flask.

## Deploy

Railway auto-deploys on push to `main`. `Procfile` tells Railway's Nixpacks builder to boot `gunicorn app:app --bind 0.0.0.0:$PORT`. Env vars are managed in the Railway dashboard (`SECRET_KEY`, `DATABASE_URL`, `OPENAI_API_KEY`, `UPLOAD_DIR`, `PAST_PAPERS_DIR`, `FLASK_ENV`) — see `RAILWAY.md`.

## Folder structure

```
Smart-igcse-platform/
├── app.py                  ← Flask factory (create_app) + module-level `app` for gunicorn
├── config.py               ← Env-var-driven Config class + validate()
├── extensions.py           ← db / login_manager / migrate singletons
├── Procfile                ← Railway boot command
├── .python-version         ← 3.12.3 pin for Nixpacks/pyenv
├── requirements.txt        ← Pinned deps (compatible-release)
├── .env.example            ← Template for local .env
├── templates/
│   ├── base.html           ← Layout wrapper (url_for static, {% block %} slots)
│   └── index.html          ← Extends base; topic recap content
├── static/
│   ├── css/style.css       ← Design tokens + all styling
│   └── js/app.js           ← Topic filter, dark-mode toggle, keyboard shortcuts
├── migrations/             ← Alembic (empty versions/ until Phase 1)
├── tests/
│   ├── conftest.py         ← SQLite-in-memory fixtures
│   ├── test_config.py      ← Env-var normalisation + validation
│   └── test_smoke.py       ← Factory + / + /health + static endpoints
└── .claude/state/          ← plan.md, phase-0-plan.md, todo.md, abbreviations.md
```

## Features (current static page)

- 7 topic cards with formulas, examples, and quick-recall tips (Irrationals, Compound interest, Probability, Functions, Vectors, Motion graphs, Differentiation).
- Topic filter nav; click to isolate a single topic or "All topics".
- Dark-mode toggle (◐ top-right), persisted in `localStorage` under `igcse-theme`.
- Keyboard shortcuts: `1`–`7` jump to topic, `a` or `0` show all, `d` toggles dark mode.
- Print-friendly: nav + toggle hide on print; all cards forced visible.

## Editing content

Topic content lives in `templates/index.html` as plain HTML inside `<article class="topic-card">` blocks. CSS tokens in `static/css/style.css` under `:root` (light) and `body.dark-mode` (dark). New components MUST use `var(--color-...)` tokens — hard-coded colours break dark mode.
