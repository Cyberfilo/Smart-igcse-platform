# Railway setup

Single-service deployment of the Smart IGCSE Platform. Flask app + Postgres + persistent volume, all under one Railway project.

## One-time setup (do this now)

### 1. Create the project

1. Go to [railway.app/new](https://railway.app/new).
2. **Deploy from GitHub repo** → pick `Cyberfilo/Smart-igcse-platform`.
3. Railway will auto-detect Python and try to deploy. It will fail until Phase 0 adds `requirements.txt` + `Procfile` — that's expected. Continue with the rest of the setup regardless.

### 2. Add Postgres

1. In the project dashboard → **+ New** → **Database** → **Add PostgreSQL**.
2. Railway creates a `Postgres` service alongside the app service.
3. On the app service → **Variables** tab → **Add Reference** → select `Postgres.DATABASE_URL`. This wires the DB URL in automatically; you never paste it.

### 3. Add persistent volume

1. On the app service → **Settings** → **Volumes** → **+ New Volume**.
2. Name: `data`. Mount path: `/data`.
3. This survives redeploys. Past-paper PDFs, extracted images, and student working uploads live here.

### 4. Environment variables

On the app service → **Variables** tab, set:

| Key | Value | Notes |
|-----|-------|-------|
| `DATABASE_URL` | *(reference)* | Set in step 2 above — leave as is. |
| `SECRET_KEY` | random 32+ bytes | Flask session-cookie signing. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `OPENAI_API_KEY` | your key | Used for GPT vision (extraction + handwriting) and revision-note generation. |
| `UPLOAD_DIR` | `/data/student-uploads` | Where student working photos are stored. |
| `PAST_PAPERS_DIR` | `/data/past-papers` | Where admin-uploaded PDFs live. |
| `FLASK_ENV` | `production` | Disables debug mode in prod. |

### 5. Domain

1. On the app service → **Settings** → **Networking** → **Generate Domain** (creates something like `smart-igcse-platform-production.up.railway.app`). Copy that hostname.
2. In Cloudflare → DNS for `menghi.dev` → delete the existing `igcse` tunnel record → add a **CNAME** record:
   - Name: `igcse`
   - Target: `smart-igcse-platform-production.up.railway.app`
   - Proxy status: Proxied (orange cloud) — gives you Cloudflare's TLS + cache in front.
3. Back on Railway → **Settings** → **Networking** → **Custom Domain** → add `igcse.menghi.dev`. Railway provisions an edge cert. No Cloudflare Origin Certificate needed when Cloudflare is proxying.

### 6. Start command

Once Phase 0 adds the scaffolding, Railway will read `Procfile`:
```
web: gunicorn app:app
```
Nothing manual needed.

## Dev loop (no more localhost)

Every change → push to a branch → Railway auto-deploys a **preview environment** with its own URL. Test there, merge to `main` when green.

For tight-feedback iteration without full redeploy, use Railway CLI:

```bash
brew install railway     # or: npm i -g @railway/cli
railway login
railway link             # once per clone
railway run python app.py
```

`railway run` injects the real `DATABASE_URL`, `OPENAI_API_KEY`, etc. into your local shell so the Flask dev server runs against the real Railway Postgres + Volume. This is the closest thing to "local dev" you get in the Railway-only world — and it's fine for iteration because the dev DB is still the Railway service DB unless you add a separate dev environment.

## Two-environment setup (optional, recommended once Phase 2+)

To avoid dev work trashing the student-facing prod DB:

1. Railway → project → **New Environment** → `staging`.
2. Staging gets its own Postgres + Volume + env vars.
3. `main` branch deploys to `production`. `staging` branch deploys to `staging`. Other branches → preview deploys.
4. `railway run --environment staging python app.py` to point the local process at staging.

Set this up before Phase 3 at the latest — once past-paper data starts accumulating, you don't want to wipe it.

## Cost watch

- Postgres + app + volume ≈ $5–15/mo under normal load.
- The real cost risk is `OPENAI_API_KEY` usage (Phase 5 vision calls + Phase 6 note generation). Monitor at platform.openai.com/usage. Phase 8 adds a per-user daily cap.
