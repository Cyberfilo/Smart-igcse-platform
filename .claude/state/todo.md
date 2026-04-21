# IGCSE 0580 Recap — TODO

## Phase 0 — execution (branch `phase-0-scaffolding`)

Detailed plan: `.claude/state/phase-0-plan.md` §5 Task breakdown.

- [x] T1 pin python 3.12.3 + expand `requirements.txt` (10 deps)
- [x] T2 `config.py` + `tests/conftest.py` + `tests/test_config.py`
- [x] T3 `extensions.py` (db / login_manager / migrate singletons)
- [x] T4 refactor `app.py` → `create_app()` factory + module-level `app`
- [x] T5 `git mv css/ static/css/`, `git mv js/ static/js/`
- [x] T6 `templates/base.html` + `templates/index.html` (body copied from old `index.html:11-244`); deleted root `index.html`
- [x] T7 `/health` route + smoke test (pytest 8/8 green locally)
- [x] T8 `flask --app app db init` → `migrations/` committed
- [x] T9 `Procfile` + `.env.example` + `.gitignore` additions
- [x] T10 rewrite `README.md` dev-loop section + sync state files
- [ ] T11 push branch + preview deploy green + 10 smoke-tests (USER ACTION — requires Railway CLI / GitHub push)
- [ ] T12 merge PR + prod deploy green + 10 smoke-tests against `igcse.menghi.dev` (USER ACTION)
- [ ] Confirm actual GPT model available (user said GPT-5.4 — verify or fall back to GPT-5 / GPT-4o vision at Phase 5 prototype kickoff)

## Phase 1 — data model + syllabus selector + Notes page (branch `phase-1-models-notes`)

- [ ] P1.1 Models: `Syllabus`, `Paper`, `Session`, `Topic`, `Cohort`, `Note` in `models.py`
- [ ] P1.2 First migration: `flask db migrate -m "phase 1 models"` → review → `flask db upgrade`
- [ ] P1.3 Seed script `scripts/seed_syllabi.py` — 0580 (P2/P4) + 0654 (P2 MCQ/P4/P6) + current 7 0580 topics
- [ ] P1.4 `/syllabus` selector route (GET list, POST store in session)
- [ ] P1.5 `/notes` page rendered from DB; HTMX partial at `/notes/<topic_id>/partial` returning a `.topic-card` fragment
- [ ] P1.6 HTMX via CDN script tag in `templates/base.html` (no build step)
- [ ] P1.7 Move current hand-written topic content into `Note` seed rows so `/notes` matches today's page

## Phase 2 — managed auth (branch `phase-2-auth`)

- [ ] P2.1 `User` model (email, password_hash, role, cohort_id, syllabus_id) + bcrypt
- [ ] P2.2 Real `@login_manager.user_loader` replacing Phase 0 stub
- [ ] P2.3 `/login` + `/logout` + session middleware
- [ ] P2.4 `@login_required` on all non-auth routes
- [ ] P2.5 `/admin/users` with "Create user" → `secrets.token_urlsafe(16)` → flash once
- [ ] P2.6 Admin-only decorator + 403 for students hitting /admin

## Phase 3 — past-paper ingestion (branch `phase-3-ingestion`)

- [ ] P3.1 `PastPaper`, `Question`, `SubPart` models; `answer_schema` enum (scalar/multi_cell/mcq/graphical)
- [ ] P3.2 Admin PDF-pair upload route (question + marking scheme) → `/data/past-papers/`
- [ ] P3.3 Extraction worker: GPT vision loop over pages 3–18 → `Question` records `extraction_status='auto'`
- [ ] P3.4 Marking-scheme parser: pages 6–10 → `SubPart.marking_alternatives[]` with oe/nfww/isw/FT conventions
- [ ] P3.5 `/admin/review/<question_id>` queue; publish flips to `admin_approved`
- [ ] P3.6 Pilot on mock PDFs at `/Users/filippomattiamenghi/Downloads/mock-*.pdf` first

## Phase 4 — Exercise page (digital-input only, branch `phase-4-exercise`)

- [ ] P4.1 `/exercise` syllabus-scoped selector (topic → paper → variant → difficulty)
- [ ] P4.2 Render `SubPart.body_html` via existing `.topic-card` primitives
- [ ] P4.3 `/media/<path>` auth-gated diagram server with path-traversal guard
- [ ] P4.4 Handle mcq + scalar + 0654 P2 auto-marking; `Attempt` record write
- [ ] P4.5 NO OCR yet — deliberately vision-free so Phase 5 risk sits on a working skeleton

## Phase 5 — handwriting OCR + diagnostic feedback (branch `phase-5-ocr`, FLAGSHIP RISK)

**Gated by the parallel prototype's GREEN verdict (see below).**

- [ ] P5.1 Photo-upload UI on non-MCQ SubParts; POST to `/attempt/<subpart_id>/photo`
- [ ] P5.2 Vision call with finalised prompt; returns `{transcript, steps, verdict, suggested_correction, error_tags}`
- [ ] P5.3 Render via existing `.tip-box` (amber — "faster way") + `.example-box` (red — "error + correction")
- [ ] P5.4 Attempt persistence + error-tag emission
- [ ] P5.5 Per-user daily vision-call cap (cost guard, hardened in Phase 8)

## Phase 6 — learning-style onboarding + personalised Revision (branch `phase-6-style-revision`)

- [ ] P6.1 `/onboarding/style` 5–7 question quiz → `User.learning_style_profile` ∈ {schema_heavy, narrative, formula_first, worked_example}
- [ ] P6.2 `/revision` page: pull `ErrorProfile`-weighted topics, generate notes via GPT with per-style system prompt
- [ ] P6.3 `RevisionNote` cache keyed `(user_id, topic_id, style, cache_key)`
- [ ] P6.4 Same content, 4 style variants — enforce via prompt tests

## Phase 7 — error-profile → revision feedback loop (branch `phase-7-loop`)

- [ ] P7.1 `Attempt` verdict ≠ correct_optimal bumps `ErrorProfile(user_id, topic_id, count, weight, last_seen)`
- [ ] P7.2 Cache invalidation trigger when error-profile delta crosses threshold
- [ ] P7.3 Next `/revision` visit regenerates with fresh error context

## Phase 8 — prod hardening (branch `phase-8-hardening`)

- [ ] P8.1 `RateLimit(user, day, endpoint)` per-user daily caps
- [ ] P8.2 `/admin/cost` — OpenAI `/v1/usage` pull + per-user breakdown
- [ ] P8.3 Postgres snapshots + `/data` export to R2 for DR
- [ ] P8.4 `gunicorn --workers 2 --timeout 120`; structured JSON logging + request-ID middleware
- [ ] P8.5 Optional staging Railway environment
- [ ] P8.6 Revisit `plan.md` "Not yet decided" items for close-out

## Phase 5 prototype (parallel, starts day 1 of Phase 1)

Runs on throwaway branch `prototype/phase-5-ocr`. Full spec: `phase-0-plan.md` §9.

- [ ] Collect 20-photo handwriting corpus into `prototype-data/handwriting/` (gitignored)
- [ ] Build minimal `/prototype/diagnose` endpoint
- [ ] Evaluation harness + go/no-go report at `.claude/state/phase-5-feasibility.md`
- [ ] Commit finalised prompt (on GREEN or AMBER→GREEN) to `.claude/state/phase-5-prompt.md`
- [ ] Update `plan.md` §"LLM integration" with confirmed model + cost-per-call + failure modes

## Phase 3 pilot input (deferred until Phase 3 begins)

- [ ] Copy `/Users/filippomattiamenghi/Downloads/mock-question-paper.pdf` + `mock-marking-scheme.pdf` into `pilot-data/` (gitignored) for extraction pilot

## Done — Session 2026-04-21 (Phases 0-8 consolidated build)

- [x] Phase 1-8 all code-complete locally; 37/37 pytest green
- [x] Models: Syllabus, Paper, Session, Topic, Note, Cohort, User, PastPaper, Question, SubPart, Attempt, RevisionNote, ErrorProfile, RateLimit
- [x] Routes: `pages_bp`, `api_bp`, `admin_bp`, `media_bp`, `prototype_bp` — full HTML + HTMX + JSON surface
- [x] Services: `openai_client`, `marking`, `ocr`, `ingestion`, `revision`, `style_classifier`, `ratelimit` — all gated by per-feature env flags
- [x] Templates: notes, syllabus, login, exercise, onboarding, revision, admin/{dashboard,users,upload_paper,review_queue,review_question,cost}, partial _topic_card
- [x] Seed script: `scripts/seed_syllabi.py` seeds 0580 (7 topics + current recap notes) + 0654 (placeholder)
- [x] One consolidated Alembic migration covering all 14 tables; applies cleanly on SQLite and (will on) Postgres
- [x] Feature flags wired: `FEATURE_OCR`, `FEATURE_INGESTION`, `FEATURE_REVISION_LLM`, `FEATURE_PROTOTYPE` — OFF by default so prod deploy with no spend is safe
- [x] Integration tests cover: login, admin user creation, RBAC block, attempt submission, error-profile bumping, style classification, revision rendering, media traversal guard, rate limit 429, prototype gate

## Ready for push — USER ACTIONS

- [ ] `git add -A && git commit -m "feat: phases 0-8 consolidated scaffold"` then `git push origin main`
- [ ] Watch Railway deploy log — expect gunicorn `Listening at: http://0.0.0.0:$PORT` on first boot
- [ ] `railway run flask --app app db upgrade` to apply migration to Postgres
- [ ] `railway run python -m scripts.seed_syllabi` to populate syllabi + topics + notes
- [ ] Create first admin via `railway run python -c` snippet (see phase-0-plan.md §6 for pattern; adapt for `User` model)
- [ ] Smoke against igcse.menghi.dev: all 10 checks in phase-0-plan.md §7
- [ ] Start Phase 5 prototype on throwaway branch; do NOT flip `FEATURE_OCR=1` until GREEN

## Historical — pre-Session 2026-04-21

- [x] `git init` + `.gitignore` + initial commit + push to `github.com/Cyberfilo/Smart-igcse-platform`
- [x] Railway project linked to repo (first deploy on `c3c7cf9` failed — expected, no `Procfile`)
- [x] Railway Postgres service + `DATABASE_URL` reference on app service
- [x] Railway Volume `data` mounted at `/data`
- [x] Env vars set on Railway: `SECRET_KEY`, `OPENAI_API_KEY`, `UPLOAD_DIR=/data/student-uploads`, `PAST_PAPERS_DIR=/data/past-papers`, `FLASK_ENV=production`
- [x] Railway `*.up.railway.app` domain generated
- [x] Cloudflare DNS: `igcse` CNAME → Railway (proxied / orange cloud), old tunnel record deleted
- [x] Railway custom domain `igcse.menghi.dev` + edge certificate issued
- [x] Created `CLAUDE.md`, `plan.md`, `todo.md`, `abbreviations.md`, `RAILWAY.md`
- [x] Captured full feature spec (SaveMyExams-style platform, 3 pages, admin, multi-syllabus, personalised revision, handwriting OCR)
- [x] Resolved 9 architecture decisions (see `plan.md` → Architecture decisions)
- [x] Dropped local-run constraint; Railway-only hosting locked
- [x] Analysed mock PDFs (`0580/43` October/November 2025 + mark scheme) → extraction notes in `plan.md`
- [x] Produced detailed Phase 0 plan → `.claude/state/phase-0-plan.md`
- [x] **Phase 0 code-complete**: factory + /health + 8 green tests + Alembic scaffold + README rewrite

## Format

- Each item: `- [ ] <verb> <object> — <why / where>`
- Completed items move to `## Done — Session <date>` with date.
- Items blocked on a decision go under `## Blocked` with the blocker named.
