# Phase 0 — Scaffolding: Production-Ready Implementation Plan

> **For engineers executing this plan (including future-you):** assume zero prior context on this repo. Follow tasks in order. Every file path, command, and expected output is explicit. Steps use `- [ ]` so they can be tracked task-by-task.

**Goal:** Turn the current static single-page revision site into a Flask application factory that serves the exact same page from Railway, with Postgres + Volume wired through env vars and Alembic migrations initialised — ready for Phase 1 to start adding models. Zero feature work.

**Architecture:** Flask application factory (`create_app()`) + env-var `Config` + SQLAlchemy/Flask-Login/Flask-Migrate all `init_app()`'d but with no models yet. Current static assets move from `/css` and `/js` into Flask's `static/` convention. The hand-written `index.html` becomes two Jinja templates (`base.html` + `index.html`) with visually identical rendered output. A module-level `app = create_app()` keeps the `Procfile` trivially compatible with `gunicorn app:app`.

**Tech stack:** Python 3.12.3 · Flask 3.x · Flask-SQLAlchemy 3.1.x · Flask-Login 0.6.x · Flask-Migrate 4.x · SQLAlchemy 2.x · psycopg2-binary · gunicorn · python-dotenv · openai 1.x · pytest.

**Deployment target:** Railway monolith. Project (`Cyberfilo/Smart-igcse-platform`) already created, Postgres service attached, `data` volume mounted at `/data`, env vars set, Cloudflare DNS swapped to a proxied CNAME, custom domain `igcse.menghi.dev` provisioned with a Railway edge certificate. Phase 0 only needs code to make the existing (currently failing) deploy succeed.

---

## 0. State on 2026-04-21

### Railway infrastructure — DONE by user

All 7 steps of `RAILWAY.md` complete (confirmed by user):

1. Project linked to `github.com/Cyberfilo/Smart-igcse-platform` (first deploy on commit `c3c7cf9` **failed** as expected — no `Procfile`, no app deps).
2. Postgres service added; app service has `DATABASE_URL` set via `${{Postgres.DATABASE_URL}}` reference.
3. Volume `data` mounted at `/data` on the app service.
4. App-service variables set: `SECRET_KEY`, `OPENAI_API_KEY`, `UPLOAD_DIR=/data/student-uploads`, `PAST_PAPERS_DIR=/data/past-papers`, `FLASK_ENV=production`.
5. Railway-provisioned domain (`*.up.railway.app`) generated.
6. Cloudflare DNS: `igcse` CNAME → Railway hostname, proxied (orange cloud).
7. Railway custom domain `igcse.menghi.dev` added; edge certificate issued.

### Code — starting point

| Path | Size | Role |
|------|------|------|
| `app.py` | 10 lines | Global Flask instance, `static_folder='.'`, `static_url_path=''`, serves `index.html` from project root. |
| `index.html` | 248 lines | Hand-written HTML: header → summary grid → topic filter nav → 7 `<article class="topic-card">` blocks → strategy footer. |
| `css/style.css` | 447 lines | CSS custom-property design tokens (`:root` = light mode; `body.dark-mode` = dark). 7 topic-accent colour classes. |
| `js/app.js` | 87 lines | Vanilla IIFE: filter handler, `localStorage`-persisted dark mode (`igcse-theme`), keyboard shortcuts (`1–7`, `a`, `0`, `d`). |
| `requirements.txt` | 1 line (`Flask>=3.0`) | Placeholder from initial commit. |
| `.gitignore` | Present | Already excludes `.env`, `__pycache__`, `data/`, `pilot-data/`, `.claude/settings.local.json`, `.claude/reports/`. |
| `Procfile` | Absent | — |
| `templates/`, `static/`, `migrations/`, `tests/`, `config.py`, `extensions.py` | Absent | — |

### Constraints (LOCKED — from `.claude/state/plan.md`; do not relax)

- UI aesthetic stays visually identical to the current page — rendered DOM must reproduce current `index.html` output exactly in light and dark mode.
- No build step — no webpack/rollup/esbuild/tailwind build. HTMX (Phase 1+) will be loaded from a CDN script tag or vendored as a plain static file.
- No public signup — Phase 0 adds no auth UI; Phase 2 introduces admin-issued credentials only.
- OpenAI API key is server-side only — `OPENAI_API_KEY` is read from env, never rendered into a template or sent to the client.
- Railway-only hosting — no SQLite fallback in the running application. Tests MAY use SQLite in-memory (explicitly scoped exception; see §5).

---

## 1. File-by-file change list

### 1.1 Create

| Path | Rationale |
|------|-----------|
| `Procfile` | Tells Railway's Nixpacks builder how to boot the web process. One line: `web: gunicorn app:app --bind 0.0.0.0:$PORT`. Without this, the container has no entrypoint and Railway's deploy fails at runtime. |
| `.python-version` | Pins Python `3.12.3` for Railway/Nixpacks and for local `pyenv` users. Avoids drift between the developer machine and the deployed container. |
| `config.py` | Single source of truth for env-var reads. Normalises Railway's legacy `postgres://` scheme to `postgresql://` (SQLAlchemy 2.x is strict). `Config.validate()` fails loudly in prod if required vars are missing. |
| `extensions.py` | Declares `db = SQLAlchemy()`, `login_manager = LoginManager()`, `migrate = Migrate()` as uninitialised singletons. The factory pattern requires extensions to be instantiated at module scope so blueprints can import them without creating circular-import pain. |
| `templates/base.html` | Layout wrapper: `<head>` with `url_for('static', …)`, `{% block body %}`, `{% block scripts %}`. Phase 1+ reuses this. |
| `templates/index.html` | Extends `base.html`; the content inside `<main class="container">…</main>` from old `index.html` moves into `{% block body %}` verbatim. |
| `static/css/style.css` | Moved from `css/style.css`. Contents byte-identical — only the URL changes (`/css/style.css` → `/static/css/style.css`). |
| `static/js/app.js` | Moved from `js/app.js`. Byte-identical. |
| `tests/__init__.py` | Empty — makes `tests/` a Python package so pytest's `rootdir` detection works cleanly. |
| `tests/conftest.py` | Pytest fixture: sets SQLite-in-memory `DATABASE_URL`, tmpdir `UPLOAD_DIR`/`PAST_PAPERS_DIR`, test `SECRET_KEY`; yields `app` and `client` fixtures via the factory. |
| `tests/test_config.py` | Asserts `postgres://` → `postgresql://` normalisation and that `Config.validate()` raises `RuntimeError` when critical vars are missing in `production` mode. |
| `tests/test_smoke.py` | Asserts factory creates, `/` renders HTML with the "IGCSE 0580 Mathematics" headline and exactly 7 `class="topic-card"` occurrences, static CSS/JS endpoints serve the known signature bytes, `/health` returns `status=ok`. |
| `migrations/` (dir) | Generated by `flask --app app db init`. Commit the full directory tree (`alembic.ini`, `env.py`, `README`, `script.py.mako`, empty `versions/`). Phase 1's first `flask db migrate` drops files into `versions/`. |
| `.env.example` | Documents the six env vars. Never contains real secrets. |

### 1.2 Modify

| Path | Change | Rationale |
|------|--------|-----------|
| `app.py` | Replace the 10-line global-app with a `create_app()` factory. Register `/` → `render_template('index.html')` and `/health`. Expose module-level `app = create_app()` at the bottom for `gunicorn app:app`. Keep `if __name__ == '__main__': app.run(...)` for `railway run python app.py`. | Factory is required once Flask-Migrate enters the CLI — see the insight in §4. Also, the current `static_folder='.'` serves EVERY file at the project root (including `.env`, `RAILWAY.md`, `.git/*` under some configs). Switching to Flask's default `static_folder='static'` closes that accidental-file-leak class. |
| `requirements.txt` | Expand from `Flask>=3.0` to the full 10-entry pinned list (see §2.1). | Phase 0 adds 9 new imports; every one must be declared. |
| `.gitignore` | Append `.pytest_cache/`, `.coverage`, `htmlcov/`, `migrations/versions/__pycache__/`, `.env` (already there — double-check). | Test-runner and migration-compilation artefacts must not land in git. |
| `README.md` | Rewrite the "How to open" + "Folder structure" sections. Double-clicking `index.html` no longer renders anything (it's a Jinja template that needs the Flask server). Dev loop becomes `railway run python app.py` per `RAILWAY.md` §"Dev loop". | Old README misleads future readers into expecting an offline-openable HTML file. |
| `.claude/state/todo.md` | Move the 5 Railway-setup items into "Done — Session 2026-04-21"; add "Phase 0 task checklist" section citing §6 of this document. | Keeps the todo list as the single source of truth for what's done vs. outstanding. |
| `.claude/state/plan.md` | Append a line under "Phasing" → Phase 0: "Detailed plan → `.claude/state/phase-0-plan.md` (2026-04-21)". | Cross-reference from the high-level roadmap to this document. |

### 1.3 Delete

| Path | Rationale |
|------|-----------|
| `css/` (directory) | Moved to `static/css/`. Leaving the old path in place would have Flask serve the same stylesheet at two URLs (once the `static_folder='.'` is removed, the `/css/...` URL breaks anyway), and would confuse future maintainers. |
| `js/` (directory) | Same reasoning — moved to `static/js/`. |
| `index.html` (root) | Replaced by `templates/index.html`. If left in place AND `static_folder` stayed at root, Flask would continue serving the stale HTML at `/index.html`. With the factory's new `static_folder='static'` default this wouldn't happen, but leaving a stale copy is still a footgun. |

---

## 2. Final file contents

### 2.1 `requirements.txt`

```
# === Production deps ===
Flask>=3.0,<4.0
Flask-SQLAlchemy>=3.1,<4.0
Flask-Login>=0.6.3,<1.0
Flask-Migrate>=4.0,<5.0
SQLAlchemy>=2.0,<3.0
psycopg2-binary>=2.9,<3.0
gunicorn>=21.2,<22.0
python-dotenv>=1.0,<2.0
openai>=1.40,<2.0

# === Tests (shipped to Railway too; ~4 MB, not worth a second file for Phase 0) ===
pytest>=8.0,<9.0
```

Pinning strategy: compatible-release (`>=X.Y,<X+1.0`). Security patches come free on rebuild; major breaking changes require a manual bump. Phase 8 can introduce `pip-compile` for a fully-locked `requirements.txt` if desired.

### 2.2 `Procfile`

```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

- `app:app` — module `app`, attribute `app` (the module-level `app = create_app()`).
- `--bind 0.0.0.0:$PORT` — Railway injects `$PORT` at runtime; gunicorn's default bind is `127.0.0.1:8000` which is unreachable from Railway's router.
- Worker count + timeout are intentionally defaults for Phase 0 (gunicorn default = 1 sync worker). Phase 5 / Phase 8 will tune: `--workers 2 --timeout 120` once vision calls land.

### 2.3 `.python-version`

```
3.12.3
```

### 2.4 `config.py`

```python
"""Env-var-driven config. All runtime toggles live here."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Local dev: railway run injects env vars, but a local .env next to app.py is
# also honoured for anyone running without railway-cli. Railway prod is
# unaffected — no .env is committed or built into the image.
load_dotenv(Path(__file__).parent / ".env")


def _normalise_db_url(url: str) -> str:
    """Railway's DATABASE_URL sometimes uses the legacy 'postgres://' scheme.
    SQLAlchemy 2.x raises NoSuchModuleError on it; normalise to 'postgresql://'."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")

    SQLALCHEMY_DATABASE_URI = _normalise_db_url(os.environ.get("DATABASE_URL", ""))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Railway Postgres idles aggressively; pool_pre_ping prevents stale-conn errors.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data/student-uploads")
    PAST_PAPERS_DIR = os.environ.get("PAST_PAPERS_DIR", "/data/past-papers")

    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"

    @classmethod
    def required_in_prod(cls) -> dict[str, str]:
        """Env vars the app cannot boot without in production."""
        return {
            "SECRET_KEY": cls.SECRET_KEY,
            "DATABASE_URL": cls.SQLALCHEMY_DATABASE_URI,
            "OPENAI_API_KEY": cls.OPENAI_API_KEY,
        }

    @classmethod
    def validate(cls) -> None:
        if cls.FLASK_ENV != "production":
            return
        missing = [k for k, v in cls.required_in_prod().items() if not v]
        if missing:
            raise RuntimeError(
                f"Missing required env vars in production: {missing}. "
                "Set them on Railway → App → Variables (see RAILWAY.md §4)."
            )
```

### 2.5 `extensions.py`

```python
"""Uninitialised Flask extension singletons. init_app() is called in create_app()."""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


# Phase 2 will set login_manager.login_view = 'auth.login' and register the real
# User-model loader. For Phase 0 a stub keeps flask-login from warning on import.
@login_manager.user_loader
def _noop_user_loader(user_id):  # noqa: ARG001 — signature fixed by flask-login
    return None
```

### 2.6 `app.py`

```python
"""Application factory + module-level `app` for gunicorn."""
import os

from flask import Flask, render_template
from sqlalchemy import text

from config import Config
from extensions import db, login_manager, migrate


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Fail fast in prod if required env vars are missing. Dev bypasses this.
    config_class.validate()

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Ensure Railway-volume subdirs exist. Idempotent, cheap, prevents first-use
    # errors in Phase 3+ when admin uploads start hitting PAST_PAPERS_DIR.
    for path in (app.config["UPLOAD_DIR"], app.config["PAST_PAPERS_DIR"]):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            # Volume not mounted (e.g. containerless dev). Log and continue.
            app.logger.warning("Data dir %s not writable on startup", path)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        """Deploy smoke test. Probes the two external dependencies (Postgres,
        volume). Returns 200 with status=ok iff both are healthy."""
        checks: dict[str, str] = {"status": "ok"}

        try:
            db.session.execute(text("SELECT 1"))
            checks["db"] = "connected"
        except Exception as e:
            checks["db"] = f"error: {type(e).__name__}"
            checks["status"] = "degraded"

        try:
            probe = os.path.join(app.config["UPLOAD_DIR"], ".health-probe")
            os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            checks["volume"] = "writable"
        except Exception as e:
            checks["volume"] = f"error: {type(e).__name__}"
            checks["status"] = "degraded"

        return checks

    return app


# Gunicorn entrypoint (`gunicorn app:app`).
app = create_app()


if __name__ == "__main__":
    # `railway run python app.py` or `python app.py` (with .env supplied).
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)
```

### 2.7 `templates/base.html`

```jinja
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}IGCSE 0580 — Topics Recap Map{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
  {% block head_extra %}{% endblock %}
</head>
<body>
  {% block body %}{% endblock %}
  <script src="{{ url_for('static', filename='js/app.js') }}"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

### 2.8 `templates/index.html`

```jinja
{% extends "base.html" %}

{% block body %}
  {# Copy the content of the current index.html from line 11 (<main class="container">) #}
  {# through line 244 (</main>) byte-for-byte into this block. No changes — the base #}
  {# template provides <!DOCTYPE>, <head>, <title>, CSS link, and trailing <script>. #}
  {# Visual output after render MUST match current igcse.menghi.dev pixel-for-pixel. #}
  <main class="container">
    <!-- ... see index.html:11–244 ... -->
  </main>
{% endblock %}
```

When executing Task 6, copy the exact byte range `index.html:11–244` (inclusive of opening `<main class="container">` through closing `</main>`) into the block. No other edits.

### 2.9 `tests/conftest.py`

```python
"""Test-time environment setup. Uses SQLite in-memory for Phase 0 because there
are no models to migrate; the `SELECT 1` probe in /health works on any DB. This
is explicitly allowed by plan.md's 'Railway-only hosting' constraint since it
covers the app runtime, not the test fixture."""
import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PAST_PAPERS_DIR", str(tmp_path / "papers"))
    monkeypatch.setenv("FLASK_ENV", "testing")


@pytest.fixture
def app():
    # Reload config so env-var changes from the autouse fixture take effect
    # (config.py resolves env at import time, which happens before fixtures run
    # on a cold test process).
    from importlib import reload

    import config

    reload(config)
    from app import create_app

    yield create_app(config.Config)


@pytest.fixture
def client(app):
    return app.test_client()
```

### 2.10 `tests/test_config.py`

```python
import pytest


def test_postgres_url_normalised(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/d")
    from importlib import reload

    import config

    reload(config)
    assert config.Config.SQLALCHEMY_DATABASE_URI.startswith("postgresql://")


def test_validate_raises_on_missing_vars_in_prod(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from importlib import reload

    import config

    reload(config)
    with pytest.raises(RuntimeError, match="Missing required env vars"):
        config.Config.validate()


def test_validate_noop_in_dev(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from importlib import reload

    import config

    reload(config)
    # Must NOT raise — dev mode tolerates missing vars so `python app.py` works.
    config.Config.validate()
```

### 2.11 `tests/test_smoke.py`

```python
def test_app_factory_creates(app):
    assert app is not None
    assert app.url_map is not None


def test_index_serves_homepage(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.data
    assert b"IGCSE 0580 Mathematics" in body
    # Exactly 7 topic cards, matching the current page verbatim.
    assert body.count(b'class="topic-card"') == 7
    # Summary grid must include the live exam date.
    assert b"29 Apr 2026" in body


def test_static_css_served(client):
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    # Design-token custom property — signature of this stylesheet.
    assert b"--color-background-primary" in response.data


def test_static_js_served(client):
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    # localStorage key for dark-mode persistence — signature of this JS.
    assert b"igcse-theme" in response.data


def test_health_endpoint_reports_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    # On SQLite in-memory + tmpdir volume, both probes succeed.
    assert payload["status"] == "ok"
    assert payload["db"] == "connected"
    assert payload["volume"] == "writable"
```

### 2.12 `.env.example`

```
# Copy to .env for local dev (git-ignored). On Railway, set these in the
# dashboard — a .env file does NOT get built into the container.

SECRET_KEY=generate-via-python--c-import-secrets-print-secrets-token_urlsafe-48
DATABASE_URL=postgresql://user:password@localhost:5432/igcse
OPENAI_API_KEY=sk-...
UPLOAD_DIR=./data/student-uploads
PAST_PAPERS_DIR=./data/past-papers
FLASK_ENV=development
```

### 2.13 `.gitignore` additions

Append these lines to the existing `.gitignore`:

```
# Testing
.pytest_cache/
.coverage
htmlcov/

# Migrations compiled bytecode
migrations/versions/__pycache__/
```

---

## 3. Post-Phase-0 directory layout

```
igcse-0580-recap/
├── .claude/
│   └── state/
│       ├── abbreviations.md
│       ├── phase-0-plan.md          ← THIS DOCUMENT (new)
│       ├── plan.md                  ← modified (pointer to this doc)
│       └── todo.md                  ← modified (Railway items → Done)
├── .env.example                     ← new
├── .gitignore                       ← modified (test / migrations cache)
├── .python-version                  ← new (3.12.3)
├── CLAUDE.md
├── Procfile                         ← new (gunicorn app:app --bind 0.0.0.0:$PORT)
├── RAILWAY.md
├── README.md                        ← rewritten (no more "double-click index.html")
├── app.py                           ← rewritten (factory + / + /health)
├── config.py                        ← new (env + pg:// normalisation + validate)
├── extensions.py                    ← new (db, login_manager, migrate)
├── migrations/                      ← new, from `flask --app app db init`
│   ├── alembic.ini
│   ├── env.py
│   ├── README
│   ├── script.py.mako
│   └── versions/                    ← empty until Phase 1
├── requirements.txt                 ← expanded (10 deps)
├── static/
│   ├── css/
│   │   └── style.css                ← moved from css/ (byte-identical)
│   └── js/
│       └── app.js                   ← moved from js/ (byte-identical)
├── templates/
│   ├── base.html                    ← new (layout; url_for('static', …))
│   └── index.html                   ← new (extends base; body = old index body)
└── tests/
    ├── __init__.py                  ← new (empty package marker)
    ├── conftest.py                  ← new (env-var + client fixtures)
    ├── test_config.py               ← new (normalisation + validate)
    └── test_smoke.py                ← new (factory + routes + static + /health)
```

**Removed vs. starting point:** `css/`, `js/`, `index.html` (at root).
**Unchanged in structure:** `.claude/`, `CLAUDE.md`, `RAILWAY.md`, `.gitignore` (content modified).

---

## 4. Implementation notes / design rationale

### 4.1 Why factory pattern now, not "when we need blueprints"

Once Flask-Migrate lands, the `flask db` CLI imports your app module to discover the `Migrate` instance. If `app.py` instantiates `Flask(__name__)` and attaches extensions at module scope (today's pattern), the CLI works — until you add your first model. Then the import chain becomes `app.py → models/__init__.py → app.py (for db)`, which is a cycle. The factory pattern (`create_app()`) breaks the cycle: `models/__init__.py` imports `db` from `extensions.py`, not from `app.py`. Introducing the factory in Phase 0, before any model exists, is the cheapest time to do it.

### 4.2 Why `static_folder='static'` (the default) instead of keeping `static_folder='.'`

The current app serves the entire project root at `/`. That means `/RAILWAY.md`, `/.gitignore`, and `/config.py` (once it exists) are all publicly fetchable. Switching to Flask's default (`static_folder='static'`) scopes public files to the `static/` dir — anything outside it is 404. This also closes the "routing collision" footgun flagged in `CLAUDE.md` § "Adding an API later".

### 4.3 Why pin `psycopg2-binary` and not `psycopg[binary]` (psycopg3)

Plan spec explicitly names `psycopg2-binary`. Flask-SQLAlchemy 3.1+ supports both; psycopg3 is newer and faster, but all the existing Flask + Railway + SQLAlchemy docs assume psycopg2. Sticking with psycopg2-binary keeps the stack "boring". Phase 8 can evaluate a psycopg3 migration if there's a performance reason.

### 4.4 Why SQLite in-memory for tests — doesn't plan.md forbid SQLite?

`plan.md` § Architecture decisions → row 1: "Railway Postgres (only — no SQLite fallback). Rationale: Railway-only hosting means single environment." The rule governs the **running application**, not the test harness. Phase 0 has zero schema — `/health` does `SELECT 1`, which works on any SQL backend — so the test fixture picks SQLite for speed and zero-dep-on-network. Phase 1+ tests that exercise migrations will need to decide: either (a) stand up a disposable Postgres via docker-compose for CI, or (b) keep SQLite for unit tests + add migration tests against a Railway `staging` environment. That decision is deferred to Phase 1's plan.

### 4.5 Why `/health` probes BOTH Postgres and the Volume

Phase 0's sole deliverable is "Railway infrastructure is correctly wired". Two things can silently misconfigure and go unnoticed until Phase 1 or Phase 3 trips over them:
- `DATABASE_URL` missing or wrong (app boots, GET `/` works, but every DB read in Phase 1 raises `OperationalError`).
- Volume not mounted or permissions wrong (app boots, GET `/` works, but every admin upload in Phase 3 raises `PermissionError`).

A single endpoint that asserts both in one HTTP call is the cheapest possible regression guard. Railway can later be configured to point its built-in healthcheck at `/health`, auto-restarting on `degraded`.

### 4.6 Why dev `validate()` is a no-op

Running `python app.py` with no `.env` is a legitimate workflow for "tweak a CSS variable, reload the browser". Demanding `DATABASE_URL` at that moment forces every dev-loop start through `railway run`, which is slower (CLI roundtrip) and requires internet. The `FLASK_ENV=production` gate is the cheap way to keep prod strict without punishing dev.

---

## 5. Task breakdown (bite-sized, one commit per task)

All tasks land on branch `phase-0-scaffolding`, created from `main` at commit `c3c7cf9` (the initial scaffolding commit). PR is opened against `main` after Task 11.

### Task 1: Pin Python + expand dependencies

**Files:** Create `.python-version`. Overwrite `requirements.txt`.

- [ ] **1.1** Write `.python-version` with single line `3.12.3`.
- [ ] **1.2** Overwrite `requirements.txt` with the content in §2.1.
- [ ] **1.3** Verify deps resolve cleanly: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
  - **Expected:** all packages install with no version-conflict errors. Takes ~60s on first run (psycopg2-binary + openai pull several transitive deps).
- [ ] **1.4** Commit:
  ```bash
  git add .python-version requirements.txt
  git commit -m "chore(phase-0): pin python 3.12.3, expand deps for flask factory"
  ```

### Task 2: Config module + tests

**Files:** Create `config.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`.

- [ ] **2.1** Write `config.py` per §2.4.
- [ ] **2.2** Write `tests/__init__.py` (empty — `touch tests/__init__.py`).
- [ ] **2.3** Write `tests/conftest.py` per §2.9.
- [ ] **2.4** Write `tests/test_config.py` per §2.10.
- [ ] **2.5** Run `pytest tests/test_config.py -v`.
  - **Expected:** 3 passed. If `pytest` isn't found: `pip install -r requirements.txt` inside the venv.
- [ ] **2.6** Commit:
  ```bash
  git add config.py tests/__init__.py tests/conftest.py tests/test_config.py
  git commit -m "feat(phase-0): env-var config with postgres:// normalisation"
  ```

### Task 3: Extensions module

**Files:** Create `extensions.py`.

- [ ] **3.1** Write `extensions.py` per §2.5.
- [ ] **3.2** No dedicated test — coverage comes from Task 4's factory test (importing `extensions` is the test).
- [ ] **3.3** Commit:
  ```bash
  git add extensions.py
  git commit -m "feat(phase-0): uninitialised SQLAlchemy/LoginManager/Migrate"
  ```

### Task 4: Refactor `app.py` into factory

**Files:** Rewrite `app.py`. Create `tests/test_smoke.py` (partial — just the factory test for now).

- [ ] **4.1** Replace `app.py` with the content in §2.6. Keep the module-level `app = create_app()` so `gunicorn app:app` still resolves.
- [ ] **4.2** Add `tests/test_smoke.py` with only `test_app_factory_creates` from §2.11 for now. (Other tests land in later tasks as the features they cover are added.)
- [ ] **4.3** Run `pytest tests/test_smoke.py::test_app_factory_creates -v`.
  - **Expected:** 1 passed.
  - **Expected:** the test's `render_template` call has no templates yet — but `test_app_factory_creates` doesn't hit `/`, just `create_app()`. So this passes.
- [ ] **4.4** Commit:
  ```bash
  git add app.py tests/test_smoke.py
  git commit -m "feat(phase-0): flask application factory with extensions wired"
  ```

### Task 5: Move static assets

**Files:** Move `css/` → `static/css/`, `js/` → `static/js/`.

- [ ] **5.1** Create `static/` directory structure:
  ```bash
  mkdir -p static
  git mv css static/css
  git mv js static/js
  ```
- [ ] **5.2** Verify no broken references: `grep -rn 'href="css/\|src="js/' . --include='*.html' --include='*.md'` should only match `README.md` (to be rewritten in Task 10) and — intentionally — the still-existing root `index.html` (to be deleted in Task 6).
- [ ] **5.3** Commit:
  ```bash
  git add -A
  git commit -m "refactor(phase-0): move static assets into flask static/ convention"
  ```

### Task 6: Build templates + route wiring

**Files:** Create `templates/base.html`, `templates/index.html`. Delete root `index.html`.

- [ ] **6.1** Create `templates/base.html` per §2.7.
- [ ] **6.2** Create `templates/index.html` per §2.8 — copy lines 11–244 of the current `index.html` verbatim into `{% block body %}`.
- [ ] **6.3** Delete root `index.html`:
  ```bash
  git rm index.html
  ```
- [ ] **6.4** Append the remaining tests in `tests/test_smoke.py` (`test_index_serves_homepage`, `test_static_css_served`, `test_static_js_served`) per §2.11.
- [ ] **6.5** Run `pytest tests/test_smoke.py -v`.
  - **Expected:** 4 passed (factory + index + css + js).
- [ ] **6.6** Visual check — run `railway run python app.py`, open `http://localhost:5000`, compare side-by-side with `https://igcse.menghi.dev` (in another tab — the old Cloudflare tunnel is gone, so the "before" reference should come from a screenshot saved before the DNS swap). **Required:** pixel-identical render in both light and dark mode.
  - If visual diff fails: inspect the rendered HTML at `view-source:` — most likely cause is that the block copy missed a line or whitespace. `diff <(curl -s localhost:5000) <(cat index.html.backup)` will pinpoint it.
- [ ] **6.7** Commit:
  ```bash
  git add templates/ tests/test_smoke.py
  git commit -m "feat(phase-0): jinja templates replacing static index.html"
  ```

### Task 7: `/health` endpoint + test

**Files:** `app.py` (health route is already in §2.6; add the test), `tests/test_smoke.py`.

- [ ] **7.1** Confirm `/health` is present in `app.py` per §2.6 (it should already be from Task 4).
- [ ] **7.2** Append `test_health_endpoint_reports_healthy` to `tests/test_smoke.py` per §2.11.
- [ ] **7.3** Run `pytest tests/test_smoke.py::test_health_endpoint_reports_healthy -v`.
  - **Expected:** 1 passed.
- [ ] **7.4** Commit:
  ```bash
  git add tests/test_smoke.py
  git commit -m "test(phase-0): /health endpoint assertion against sqlite + tmpdir"
  ```

### Task 8: Initialise Alembic migrations directory

**Files:** Generated `migrations/` dir.

- [ ] **8.1** Run `railway run flask --app app db init`.
  - **Expected:** creates `migrations/alembic.ini`, `migrations/env.py`, `migrations/README`, `migrations/script.py.mako`, `migrations/versions/` (empty).
  - **If Railway CLI isn't available:** `FLASK_APP=app SECRET_KEY=x DATABASE_URL=sqlite:///tmp.db OPENAI_API_KEY=x flask db init` works locally, then delete `tmp.db` after.
- [ ] **8.2** Commit:
  ```bash
  git add migrations/
  git commit -m "feat(phase-0): alembic migrations dir (no migrations yet — phase 1)"
  ```

### Task 9: `Procfile` + `.env.example` + `.gitignore`

**Files:** Create `Procfile`, `.env.example`. Append to `.gitignore`.

- [ ] **9.1** Write `Procfile` per §2.2.
- [ ] **9.2** Write `.env.example` per §2.12.
- [ ] **9.3** Append test/migration cache lines to `.gitignore` per §2.13.
- [ ] **9.4** Commit:
  ```bash
  git add Procfile .env.example .gitignore
  git commit -m "feat(phase-0): procfile + .env.example + gitignore test caches"
  ```

### Task 10: Docs sync

**Files:** Rewrite `README.md`. Update `.claude/state/todo.md`. Update `.claude/state/plan.md`.

- [ ] **10.1** Rewrite `README.md` "How to open" and "Folder structure" sections. New content: repo is a Flask app deployed on Railway at `igcse.menghi.dev`; dev loop is `railway run python app.py`; folder structure section reflects §3.
- [ ] **10.2** Edit `.claude/state/todo.md` — move Railway-setup items into "Done — Session 2026-04-21"; add a "Phase 0 — execution" section pointing to this plan.
- [ ] **10.3** Edit `.claude/state/plan.md` — under the "Phasing" → Phase 0 line, append "Detailed plan → `.claude/state/phase-0-plan.md` (2026-04-21)".
- [ ] **10.4** Commit:
  ```bash
  git add README.md .claude/state/todo.md .claude/state/plan.md
  git commit -m "docs(phase-0): update readme + state files for factory dev loop"
  ```

### Task 11: Preview-deploy verification (branch push)

- [ ] **11.1** Push the branch: `git push -u origin phase-0-scaffolding`.
- [ ] **11.2** In the Railway dashboard → Deployments tab, wait for the preview deploy of `phase-0-scaffolding` to go green. Expect build time ~2 min (installing 10 pip deps).
  - **If build fails:** read Railway logs. 90% of first-deploy failures here are (a) psycopg2-binary needing a build toolchain (Nixpacks handles this by default, but if Railway picks `python:3.12-slim` as the base you need `apt install -y gcc libpq-dev`) or (b) `Procfile` syntax error.
- [ ] **11.3** Copy the preview URL from the Railway dashboard (e.g. `https://smart-igcse-platform-phase-0-scaffolding.up.railway.app`).
- [ ] **11.4** Run the smoke-test script from §7 against the preview URL. All 8 curl commands must succeed.
- [ ] **11.5** If anything fails, commit fixes on the branch and push again. Do NOT merge until preview is green.

### Task 12: Merge + production verification

- [ ] **12.1** Open PR `phase-0-scaffolding` → `main`. PR body: summary of Phase 0 + link to this plan.
- [ ] **12.2** Merge (squash or merge commit — either works).
- [ ] **12.3** Railway auto-deploys `main` to the production domain `igcse.menghi.dev`. Wait for green.
- [ ] **12.4** Run the smoke-test script from §7 against `https://igcse.menghi.dev`.
- [ ] **12.5** Visual check — compare `https://igcse.menghi.dev` against the pre-swap reference screenshot (saved earlier). Pixel-identical in both light and dark mode. All keyboard shortcuts functional.
- [ ] **12.6** If any smoke test fails, revert: `git revert` the merge commit, push, let Railway redeploy to the previous-known-good state. Diagnose the failure on a new branch.

---

## 6. Railway env-var + domain swap checklist (verify state)

Cross-referencing `RAILWAY.md` section-by-section. User has confirmed steps 1–7 are complete. This table is the pre-push audit.

| `RAILWAY.md` step | Status | How to verify before pushing |
|-------------------|--------|------------------------------|
| §1 Project linked to `Cyberfilo/Smart-igcse-platform` | ✓ Done | Railway dashboard shows repo; first deploy on `c3c7cf9` failed (expected). |
| §2 Postgres service + `DATABASE_URL` reference | ✓ Done | Railway → App → Variables → `DATABASE_URL` shows `${{Postgres.DATABASE_URL}}`. |
| §3 Volume `data` mounted at `/data` | ✓ Done | Railway → App → Settings → Volumes → `data` at `/data`. |
| §4 `SECRET_KEY`, `OPENAI_API_KEY`, `UPLOAD_DIR`, `PAST_PAPERS_DIR`, `FLASK_ENV` | ✓ Done | Railway → App → Variables lists all 5 (plus the referenced `DATABASE_URL`). |
| §5 Railway domain generated | ✓ Done | Railway → App → Settings → Networking shows a `*.up.railway.app` hostname. |
| §6 Cloudflare CNAME `igcse` → Railway (proxied) | ✓ Done | `dig igcse.menghi.dev +short` returns Cloudflare edge IPs, not a Railway IP. |
| §7 Custom domain `igcse.menghi.dev` on Railway | ✓ Done | Railway → App → Settings → Networking → Custom Domain lists `igcse.menghi.dev` with an issued edge certificate. |

### Pre-push verification commands

Run these from the repo root before `git push`:

```bash
# 1. DNS resolves to Cloudflare (not 127.0.0.1, not Railway directly)
dig igcse.menghi.dev +short
#    expect: one or more CF edge IPs (proxied). If empty, Cloudflare record is wrong.

# 2. TLS terminates — even though the app is still broken pre-Phase-0, the
#    cert chain CF → Railway should already be live.
curl -sI https://igcse.menghi.dev/ | head -1
#    expect: HTTP/2 502 or 404 (app 500s / Railway proxy errors) — NOT a TLS error.
#    If you see 'SSL certificate problem', Cloudflare or Railway cert isn't issued yet.

# 3. Railway CLI sees all env vars
railway link   # once per clone — select Smart-igcse-platform / production
railway variables | grep -E 'SECRET_KEY|DATABASE_URL|OPENAI_API_KEY|UPLOAD_DIR|PAST_PAPERS_DIR|FLASK_ENV'
#    expect: all 6 listed with non-empty values
```

If any of the above fails, stop — diagnose and fix per `RAILWAY.md` before pushing Phase 0 code.

### Domain swap: no action required

The tunnel-based `igcse.menghi.dev` → local Flask route documented in the old `CLAUDE.md` was retired when the Cloudflare CNAME was added. Nothing else to swap in Phase 0 — the domain currently routes to Railway and will start serving correctly the moment a deploy succeeds.

---

## 7. Acceptance criteria — concrete smoke tests

All of these must pass against `https://igcse.menghi.dev` (production) for Phase 0 to be signed off. Same script runs against the preview URL in Task 11.

```bash
SITE="${SITE:-https://igcse.menghi.dev}"

# 1. Root returns 200 with the headline
curl -s "$SITE/" | grep -c 'IGCSE 0580 Mathematics'
#    expect: >= 1

# 2. Exactly 7 topic cards render
curl -s "$SITE/" | grep -oc 'class="topic-card"'
#    expect: 7

# 3. Summary grid has the exam date
curl -s "$SITE/" | grep -c '29 Apr 2026'
#    expect: >= 1

# 4. Static CSS served with correct content-type
curl -sI "$SITE/static/css/style.css" | grep -Ei 'http/|content-type'
#    expect: HTTP/2 200
#            content-type: text/css; charset=utf-8

# 5. Static JS served with correct content-type
curl -sI "$SITE/static/js/app.js" | grep -Ei 'http/|content-type'
#    expect: HTTP/2 200
#            content-type: text/javascript (or application/javascript)

# 6. /health reports healthy on both probes
curl -s "$SITE/health"
#    expect: {"status": "ok", "db": "connected", "volume": "writable"}

# 7. Old paths return 404 (confirms static-folder scope moved)
curl -sI "$SITE/css/style.css" | head -1
#    expect: HTTP/2 404

# 8. Railway logs show gunicorn booted (from your terminal, Railway-linked)
railway logs --tail 50 | grep -Ei 'gunicorn|Listening at|Booting worker'
#    expect: 'Listening at: http://0.0.0.0:$PORT', 'Booting worker with pid ...', no tracebacks

# 9. Postgres reachable from the app (from Railway shell)
railway run python -c "
from app import db, create_app
app=create_app(); app.app_context().push()
from sqlalchemy import text
print(db.session.execute(text('SELECT 1')).scalar())
"
#    expect: 1

# 10. Volume writable from the app
railway run python -c "
import os
p='/data/student-uploads/.probe'
os.makedirs('/data/student-uploads', exist_ok=True)
open(p,'w').write('ok')
print(os.path.getsize(p))
os.remove(p)
"
#    expect: 2
```

### Visual / UI acceptance

- Side-by-side screenshot compare `igcse.menghi.dev` (post-Phase-0) vs. the pre-swap reference (saved before the Cloudflare tunnel was retired). **Required: pixel-identical** in both light and dark mode.
- All keyboard shortcuts still work: `1`–`7`, `a`, `0`, `d`. Topic filter toggles `.hidden` on non-matching cards, then smooth-scrolls. Dark-mode toggle persists across reload via `localStorage` key `igcse-theme`.
- Print view still hides nav + theme toggle, forces all cards visible, avoids cards page-breaking.

### Regression guard — DO NOT ship if:

- Any of the 10 commands above fails.
- Visual diff shows any spacing, colour, or font drift.
- Railway logs show `ImportError`, `OperationalError`, or `KeyError` at boot.
- `/health` returns `status: degraded`.
- `/static/*` returns 404 (indicates `static_folder` misconfigured).
- `/index.html` returns 200 at the root (indicates the stale file wasn't deleted).
- `/css/style.css` returns 200 (indicates `static_folder='.'` leaked back in).

---

## 8. Phase 1–8 outlines + cross-phase dependencies

One paragraph each. Dependencies cite the phase(s) that MUST complete first.

### Phase 1 — Data model + syllabus selector + Notes page

**Depends on:** Phase 0. **Also in flight:** Phase 5 prototype (see §9) starts on its own branch during this phase.
Write SQLAlchemy models for `Syllabus`, `Paper`, `Session`, `Topic`, `Cohort`, `Note` per the data model in `plan.md` §"Data model". Run `railway run flask --app app db migrate -m "phase-1 core schema"` then `flask db upgrade` in production. Seed 0580 (Mathematics, papers P2/P4) and 0654 (Coordinated Sciences, papers P2 MCQ / P4 / P6) plus their topic lists via a one-shot management script (`railway run python scripts/seed_syllabi.py`). Convert the current index template into a `/syllabus` selector page; on choice, session stores `syllabus_id` and the header switches between "IGCSE 0580 Mathematics" and "IGCSE 0654 Coordinated Sciences" without any visual drift. Notes page (`/notes`) lists the syllabus's topics and renders each topic's `Note.content_html` inside the existing `.topic-card` + `.formula-box` primitives — admin curation is NOT yet scoped, so every logged-in user (there is no login yet — Phase 2) sees all notes. This phase establishes the HTMX partial pattern: `/notes/<topic_id>/partial` returns a rendered `.topic-card` fragment that `hx-get` swaps in, and every subsequent phase reuses this primitive.

### Phase 2 — Managed auth (admin + student roles)

**Depends on:** Phase 1 (needs `Cohort` and — new here — `User` alongside it).
Add the `User` model (`email`, `password_hash`, `role` ∈ `{student, admin}`, `syllabus_id`, `cohort_id`, `learning_style_profile` JSON column). Wire `login_manager.user_loader` against it for real. Add `/login` with a standard Flask-WTF form that bcrypt-verifies the stored hash via `werkzeug.security.check_password_hash`. Add `/admin/users` (gated by `@admin_required` decorator) with a "Create user" button that generates a random password via `secrets.token_urlsafe(16)`, saves the hash, and displays the plaintext password ONCE in a flash banner for the admin to paste to the student — no SMTP, no magic links (deferred per plan.md §"Not yet decided"). Every non-auth route becomes `@login_required`; `/login` and `/static/*` are the only exceptions. Sessions are server-side signed cookies (already keyed from `SECRET_KEY`). Post-phase: the site is locked down; only admin-issued accounts can reach the Notes page.

### Phase 3 — Past-paper ingestion pipeline

**Depends on:** Phase 2 (admin role for upload), Phase 1 (topic tagging). **Pilot input:** the two mock PDFs at `/Users/filippomattiamenghi/Downloads/mock-question-paper.pdf` and `mock-marking-scheme.pdf` (per `plan.md` risk mitigation).
Admin uploads a pair (question paper + marking scheme) at `/admin/papers/new`; files save to `PAST_PAPERS_DIR=/data/past-papers/<syllabus>/<year>/<series>/<paper>-<variant>/` (path encodes the full code `0580/43 October/November 2025`). A synchronous per-question loop (background worker deferred to Phase 8) sends each question page as an image to GPT vision with a strict JSON-schema-enforced prompt that returns `{question_body_html, sub_parts: [...], images: [...], marks_total, suggested_topic_id, difficulty_guess}`; for each `SubPart` it also consults the marking-scheme pages (extracted separately) to populate `answer_schema` (`scalar|multi_cell|mcq|graphical`), `correct_answer`, `canonical_method`, and `marking_alternatives[]` parsed from the `Partial Marks` column (M1/M2/B1/B2, `oe`, `nfww`, `isw`, `FT`). Records land in `extraction_status='auto'` and enter a review queue at `/admin/review/<question_id>` where the admin edits/re-tags/approves — approval flips to `admin_approved` and the question becomes visible on the Exercise page. **Run the Phase 3 pilot on the mock-paper pair first; bad extraction = corrupted question bank (plan.md risk #2).** Formula sheets (page 2 of each paper per plan.md §"Past-paper extraction notes") are extracted once per syllabus+session and attached to every question of that batch as shared context.

### Phase 4 — Exercise page (digital input only, no OCR yet)

**Depends on:** Phase 3 (needs approved `Question`/`SubPart` records). **Deliberately excludes Phase 5's vision path.**
Exercise page at `/exercise` — syllabus-scoped selector (topic → paper → variant → difficulty) → backend pulls one approved `SubPart`, renders `body_html` with any extracted diagrams inline (images served via a `/media/<path>` auth-gated Flask view that checks `UPLOAD_DIR`/`PAST_PAPERS_DIR` prefix to prevent path traversal). For `answer_schema ∈ {mcq, scalar}` and for ALL 0654 Paper 2 questions (MCQ delivery), the UI shows typed input, backend auto-grades on submit, writes an `Attempt` with `verdict ∈ {correct_optimal, incorrect}` (no `correct_suboptimal` without method analysis yet). `multi_cell` and `graphical` are flagged "deferred to Phase 5" with a stub input + mark-as-correct-or-wrong self-report. This phase proves the exercise loop end-to-end without Phase 5's risk; if Phase 5's prototype (see §9) comes back red, Phase 4 is still a working MVP.

### Phase 5 — Handwriting OCR + diagnostic feedback (flagship risk)

**Depends on:** Phase 4 (exercise submit flow to hook into). **Pre-requisite:** the parallel prototype (§9) has produced a green-light feasibility report and a finalised prompt template.
Add a "photo of working" step for every `answer_schema != mcq` SubPart — user takes a phone photo, backend saves to `UPLOAD_DIR=/data/student-uploads/<user_id>/<attempt_id>.jpg`, calls GPT vision with the Phase-5-prototype-finalised prompt that packs the question, correct answer, canonical method, and marking-scheme alternatives, asking for JSON `{transcript, steps[], verdict ∈ {correct_optimal, correct_suboptimal, incorrect}, suggested_correction_html, error_tags[]}`. UI renders the verdict inline — green for optimal, amber "there was a faster way — tap to see" for suboptimal (reuses the existing `.tip-box` primitive), red "here's where it went wrong" with GPT-corrected working for incorrect (reuses `.example-box` + `.formula-box`). `error_tags` increments `ErrorProfile(user_id, topic_id, count, last_seen)` which feeds Phase 6. **Risk mitigation lives in §9 — this phase only proceeds if the prototype's go/no-go gate is met.**

### Phase 6 — Learning-style onboarding + personalised Revision page

**Depends on:** Phase 2 (needs `User.learning_style_profile`).
A bespoke 5–7 question onboarding quiz at `/onboarding/style` classifies the user as one of `{schema_heavy, narrative, formula_first, worked_example}` (decision #6 in `plan.md`) and writes the classification + per-category score to `User.learning_style_profile` as JSON. Revision page at `/revision` pulls the user's `ErrorProfile` weighted list (highest-count topics first, low-attempt gaps next) and for each topic either serves a cached `RevisionNote` or, on cache miss, calls GPT-5.4 (or fallback — verified at Phase 0 end: GPT-5, GPT-4o vision) with a per-style system prompt + the topic's canonical `Note.content_html` + the user's tagged errors, output cached in `RevisionNote(user_id, topic_id, style_used, generated_content_html, cache_key)`. Initial version: note content is the same everywhere; personalisation is rendering (schemas and diagrams for `schema_heavy`; long prose with analogies for `narrative`; formula-first reference cards for `formula_first`; dense worked-examples for `worked_example`). Revision page uses the current `.topic-card` + `.formula-box` + `.example-box` primitives — zero visual drift.

### Phase 7 — Error-profile → Revision feedback loop

**Depends on:** Phase 5 (error tagging from handwriting diagnostics), Phase 6 (RevisionNote cache).
Every new `Attempt` with verdict ≠ `correct_optimal` updates the `ErrorProfile(user_id, topic_id)` row: `count += 1`, `last_seen = now()`, `weight` rolled via exponential decay (half-life ≈ 14 days, so old errors fade as the user re-practises). When the delta since the last RevisionNote generation exceeds a threshold (either `count_delta ≥ 3` OR `topic entered top-3 errors since last generation`), the cache for `(user_id, topic_id, style)` is invalidated and the next Revision visit regenerates the note with the fresh error context baked into the system prompt. Admin dashboard at `/admin/users/<id>/profile` surfaces the user's error profile as a stacked bar (topic × error-tag) so a teacher can see at-a-glance where each student is struggling. This is the phase where the product starts to feel genuinely adaptive.

### Phase 8 — Production hardening

**Depends on:** ALL previous — this is close-out.
Introduce `RateLimit(user_id, date, endpoint, count)` with per-user per-day caps on OpenAI-backed endpoints (`/revision/<topic>/regenerate`, `/exercise/<attempt>/diagnose`). Admin cost dashboard at `/admin/cost` pulling OpenAI usage from the API (`/v1/usage`) plus the `RateLimit`-derived per-user breakdown. Nightly Postgres snapshot (Railway-native) + cron-triggered export of `/data/*` to Cloudflare R2 (or similar off-platform bucket — decision to be made in Phase 8) for disaster recovery. Gunicorn tuning (`--workers 2 --timeout 120`) to cover Phase 5 vision latency. Structured JSON logging with request-ID middleware (`X-Request-ID` header → thread-local → every log line). Optional: open a `staging` Railway environment (per `RAILWAY.md` §"Two-environment setup") so dev can `railway run --environment staging` without touching prod data. Close-out tasks: revisit `plan.md` §"Not yet decided" — confirm Flask-monolith held (no need to split to Vercel), confirm credential-paste workflow held (no SMTP needed), decide on backup bucket provider.

### Inter-phase dependency graph (text form)

```
Phase 0 (scaffolding)
  └── Phase 1 (data model + notes page)
       ├── Phase 2 (auth)
       │    ├── Phase 3 (past-paper ingestion)  ← needs admin role
       │    │    └── Phase 4 (exercise, digital-input)
       │    │         └── Phase 5 (handwriting OCR)  ← prototype §9 starts during Phase 1
       │    │              └── Phase 7 (error-profile feedback loop)
       │    └── Phase 6 (learning style + revision)  ← depends on User, parallel to 3/4/5
       │         └── Phase 7 (feedback loop)  ← also needs Phase 5
       └── Phase 8 (hardening)  ← after all previous
```

Critical path: Phase 0 → 1 → 2 → 3 → 4 → 5 → 7 → 8. Phase 6 can slot in any time after Phase 2.

---

## 9. Parallel Phase 5 prototype — handwriting OCR de-risking

**Why this is called out in the Phase 0 plan:** `plan.md` §"Biggest risks" #1 names handwriting-OCR feasibility as the single existential risk for the flagship feature. Discovering it's infeasible after Phases 1–4 (weeks of work) is unacceptable. The plan sections-off the risk into a bounded spike that runs in parallel.

**When it starts:** day one of Phase 1. NOT after Phase 4.

**Where it lives:** throwaway branch `prototype/phase-5-ocr` off `main`. **Never merges into `main`.** Deploys to its own Railway preview environment (Railway auto-previews non-main branches per `RAILWAY.md`) so vision calls hit real infrastructure (volume mount + real `OPENAI_API_KEY`). Shares `main`'s Railway Postgres read-only at first; writes only to a `prototype_`-prefixed table namespace if it needs any DB writes at all.

**Scope (3–5 working-day spike, NOT a full feature):**

1. **Handwritten-working corpus (day 1)** — the user collects 20 real phone-camera photos of their own IGCSE-style workings across 4+ topics: algebra, geometry, trigonometry, probability, plus at least one each of "correct+optimal", "correct+suboptimal/long method", "wrong by arithmetic slip", "wrong by method choice". Photos saved to `prototype-data/handwriting/<id>.jpg` (gitignored). Each has a companion `prototype-data/handwriting/<id>.yaml` with ground truth: `{question_text, correct_answer, actual_student_answer, expected_verdict, expected_error_tags}`.

2. **Minimal `/prototype/diagnose` Flask route (day 2)** — accepts `multipart/form-data` with an image + a JSON body `{subpart_id, canonical_answer, marking_alternatives}`, calls OpenAI vision (current best available: user stated GPT-5.4 — first task here is verifying availability at the platform level), returns JSON per the expected Phase 5 schema: `{transcript, steps, verdict, suggested_correction, error_tags}`.

3. **Evaluation harness (day 3)** — a pytest-driven script that POSTs each corpus item's image to the prototype endpoint and asserts the returned `verdict` matches `expected_verdict`. Also dumps per-item diff reports to `prototype-data/eval-<date>.md` for manual review of transcription quality and correction accuracy.

4. **Prompt iteration (days 3–4)** — based on initial results, iterate on the system prompt: test including vs. omitting the marking scheme alternatives, test different JSON-schema strictness levels, test including vs. omitting step-by-step reasoning scaffolding. Commit every prompt variant to `prototype-data/prompts/v<N>.md` with its accuracy score.

5. **Go/no-go report (day 5)** — write `.claude/state/phase-5-feasibility.md` with final accuracy numbers, best prompt, cost-per-call estimate, failure-mode notes, and a go/no-go verdict.

**Go/no-go gate (must pass BEFORE Phase 3 begins for real):**

| Verdict-classification accuracy on the 20-item corpus | Decision |
|-------------------------------------------------------|----------|
| **≥ 80%** | GREEN — proceed. Lock the finalised prompt template as `.claude/state/phase-5-prompt.md`. Confirm the model + fallback list in `plan.md` §"LLM integration". Commit the cost-per-call estimate to `plan.md` for Phase 8 rate-limit math. |
| **60% – 79%** | AMBER — investigate. Is failure in transcription (vision can't read the handwriting) or diagnosis (vision reads it but mis-verdicts)? Try the next-best model in the fallback list; try prompt restructuring. Extend spike by ≤ 3 days. Re-run gate. |
| **< 60%** | RED — replan Phase 5 around typed-input working (keyboard entry of steps, no photo). Error profile still works from verdicts; the handwriting photo becomes a Phase 8+ stretch goal. Update `plan.md` to reflect the pivot. |

**Hard constraints on the prototype:**

- Does NOT alter the main-branch database schema. If any DB access is needed, write to `prototype_*` tables in a separate schema.
- Does NOT expose a route to real users — `/prototype/*` is admin-only or unauthenticated on a preview URL that isn't linked from anywhere.
- Does NOT implement the Phase 5 UI — no integration with Exercise page, no `Attempt` records, no `ErrorProfile` updates. Just the `/prototype/diagnose` endpoint + evaluation harness.
- IS deleted (or archived by tag + branch delete) the moment the go/no-go report is written. Its artefacts (`phase-5-feasibility.md`, `phase-5-prompt.md`) are cherry-picked into `main`; the code is not.

**Outputs fed back into the main roadmap:**

1. `.claude/state/phase-5-feasibility.md` — accuracy numbers + go/no-go.
2. `.claude/state/phase-5-prompt.md` — finalised system prompt (only on GREEN or AMBER resolved to GREEN).
3. Update `.claude/state/plan.md` §"LLM integration" — confirmed model, cost-per-call, failure modes.
4. Update `.claude/state/plan.md` §"Biggest risks" #1 — mitigation resolved.

---

## 10. Non-goals in Phase 0 (explicit)

To prevent scope drift during execution, Phase 0 is explicitly NOT:

- Adding any business-domain model (Syllabus, User, Topic, Note — all Phase 1 or later).
- Introducing HTMX (Phase 1 — when the first dynamic partial is needed).
- Writing any `flask db migrate` migration (Phase 1 — needs a model to migrate).
- Introducing Celery, Redis, or any background-worker infrastructure (Phase 8 if needed).
- Integrating with OpenAI beyond having the env var available (Phase 3 for extraction, Phase 5 for vision).
- Adding rate-limiting middleware (Phase 8).
- Setting up a `staging` Railway environment (Phase 8, optional).
- Structured JSON logging (Phase 8).
- Writing any admin UI (Phase 2).
- Any visual/UI change — every pixel must match today's site.

If execution reveals Phase 0 "really needs" any of the above, STOP and re-plan rather than drift the scope.

---

## 11. Sign-off checklist

Phase 0 is complete when ALL of the following are true:

- [ ] Branch `phase-0-scaffolding` merged to `main`.
- [ ] Railway production deploy of `main` is green (all builds green, runtime logs clean).
- [ ] All 10 smoke-test commands in §7 pass against `https://igcse.menghi.dev`.
- [ ] Visual diff vs. pre-swap reference is pixel-identical in light and dark mode.
- [ ] All 11 tests pass locally (`pytest tests/ -v` → 11 passed).
- [ ] `.claude/state/todo.md` reflects Phase 0 done.
- [ ] `.claude/state/plan.md` Phase 0 line updated.
- [ ] `README.md` no longer tells readers to double-click `index.html`.
- [ ] Phase 5 prototype branch `prototype/phase-5-ocr` exists and has first commit (not a Phase 0 blocker — parallel track that Phase 1 picks up).

---

## Appendix A — Quick reference: command cheat sheet for Phase 0 execution

```bash
# One-time setup after cloning
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local dev (requires Railway CLI linked)
railway link                        # once per clone
railway run python app.py           # hits real Railway Postgres + volume

# Local dev (no Railway CLI — uses .env)
cp .env.example .env
# edit .env with local or staging credentials
python app.py

# Run tests
pytest tests/ -v

# Initialise migrations (Task 8 — one-time)
railway run flask --app app db init

# Deploy
git push origin phase-0-scaffolding              # preview deploy
# merge PR → main → auto-deploys production

# Smoke-test production
SITE=https://igcse.menghi.dev bash -c '
  curl -s "$SITE/" | grep -c "IGCSE 0580 Mathematics"
  curl -s "$SITE/" | grep -oc class=\"topic-card\"
  curl -s "$SITE/health"
'
```

---

## Appendix B — Plan review

Per the writing-plans skill, the final step is a plan-review dispatch. Skipped here on the user's global CLAUDE.md guidance against rubber-stamping subagents (the plan is bounded, all constraints are explicit, and the user will review this document themselves). If a second pair of eyes is wanted, dispatch `gsd-plan-checker` or similar with input `path=.claude/state/phase-0-plan.md`, `spec=.claude/state/plan.md`.
