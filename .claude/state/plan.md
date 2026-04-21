# IGCSE 0580/0654 Recap — Scaling Plan

**Last updated**: 2026-04-21 (decisions locked, local-run constraint dropped)
**Status**: 9/9 architecture decisions resolved + hosting simplified to Railway-only. Ready for detailed phase planning via `/ultraplan`.

## Product vision

Classroom-ready revision platform modelled on SaveMyExams with three differentiators:
1. **Personalised revision** — driven by user's past errors + learning-style profile.
2. **Handwritten working OCR + diagnostic feedback** — user submits photo of workings, system evaluates.
3. **Admin-curated** — admin selects which notes/topics are shown per cohort.

## Fixed constraints (carry forward; do not relax without user ok)

- **UI aesthetic stays identical** to the current static single page (design tokens in `css/style.css`, Claude-widget look). New pages reuse the same primitives — no aesthetic redesign.
- Managed login only — NO public signup, admin issues credentials.
- LLM API is **centralised** (universal env API key, NOT bring-your-own-key). System prompt is per-user and per-learning-style.
- No build step unless a decision explicitly introduces one (see decision #9 — HTMX chosen specifically to avoid this).
- **Everything on Railway** — no local-run requirement. Dev iteration via `railway run` / preview deploys.

## Hosting (locked)

- **Frontend + backend**: Railway (monolithic Flask service). HTML served from the same service that owns the DB connection.
- **Database**: Railway Postgres (added as a service in the same project).
- **File storage**: Railway Volume mounted at `/data/` (past-paper PDFs, extracted images, student working photos).
- **Domain**: `igcse.menghi.dev` → Railway's service domain via Cloudflare CNAME (the previous localhost tunnel setup is retired).
- **Dev loop**: `railway run python app.py` (or gunicorn) for local iteration against real Railway env vars + DB; push-to-branch triggers preview deploys for anything risky.

## Syllabi supported

| Code | Name | Papers tracked |
|------|------|----------------|
| 0580 | Cambridge IGCSE Mathematics | P2, P4 |
| 0654 | Cambridge IGCSE Coordinated Sciences | P2 (MCQ — digital delivery), P4, P6 |

Both syllabi share page structure; only topics differ. First-run flow: user picks syllabus → everything after is contextualised.

## Pages

### 1. Notes (universal)
- Same content for everyone.
- Admin controls which notes/topics are visible per cohort.
- Visual style = current `index.html` topic cards.

### 2. Revision (deeply personalised)
- Driven by:
  - **Error profile** — every wrong exercise attempt feeds here (topic + nature of error).
  - **Learning-style profile** — bespoke 5–7q test at onboarding classifies render preference (schema / narrative / formula-dense / worked-example).
- Output: LLM-generated notes re-rendered in the user's preferred style.
- Re-generates as the profile evolves.

### 3. Exercise (flagship surface)
Workflow:
1. User picks syllabus → topic → paper (+ variant) → difficulty.
2. System pulls a past-paper question (pre-ingested + tagged).
3. Question rendered natively, preserving diagrams.
4. **0654 P2 (MCQ)** → digital input, auto-marked.
5. **Everything else** → user enters final answer + uploads photo of working.
6. GPT vision reads handwriting, compares to correct method + marking-scheme alternatives:
   - Wrong answer → correct the working + explain.
   - Right answer, inefficient method → soft notice "there was a faster way — tap to see".
   - Right answer, good method → confirm.
7. Every error updates topic-level error profile → feeds Revision.

### 4. Admin
- Issue credentials (no self-signup) — generates random password shown to admin to paste to student.
- Select which notes/topics are exposed per user/cohort.
- Upload past-paper PDFs (saved to Railway volume) + review auto-extracted questions before publishing.
- Per-user progress dashboards.

## Architecture decisions (LOCKED)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Database | Railway Postgres (only — no SQLite fallback) | Railway-only hosting means single environment. SQLAlchemy over Postgres. |
| 2 | Backend framework | Flask + SQLAlchemy + Flask-Login + HTMX templates | Keeps current stack; adds DB + auth + server-rendered dynamic partials. |
| 3 | Past-paper storage | Railway Volume mounted at `/data/` | Same service, no external creds. PDFs under `/data/past-papers/`, student uploads under `/data/student-uploads/`. |
| 4 | OCR / vision | GPT vision (OpenAI) directly | Single provider. Handles both question extraction AND handwriting diagnosis. |
| 5 | Past-paper extraction | Hybrid — GPT auto-extracts, admin review queue, publish on approval | Automated first pass, admin approves/edits before questions go live. |
| 6 | Learning-style instrument | Bespoke 5–7q aligned to render modes | Classifies rendering preference, not cognitive style. Direct mapping to system-prompt variants. |
| 7 | Auth | Server-side sessions via Flask-Login | Simplest for Flask monolith; admin revocation trivial. |
| 8 | Credential issuing | Admin clicks "Create user" → random password generated → shown once to admin → admin copies to student | No SMTP dependency; magic-links can be added later without schema change. |
| 9 | Frontend approach | HTMX + vanilla JS, reusing existing CSS tokens | Preserves "no build step" invariant; server renders HTML partials for dynamic bits. |

## Past-paper extraction notes (from mock-paper analysis, 2026-04-21)

**Paper code format**: `0580/43` = syllabus `0580`, variant code `43`. First digit of variant = paper number (4), second digit = variant within paper (1/2/3). 0580 runs 3 variants of each paper per session — **must capture variant separately or we'll dedupe legitimate content.**

**Session format**: `October/November 2025` → `year=2025, series=O/N`. Other series: F/M (Feb/March), M/J (May/June).

**Question paper structure (20 pages typical):**
- Page 1: cover with metadata (syllabus, paper/variant, session, duration). Extract once per paper.
- Page 2: formula list. Identical across all papers of a given syllabus/series — extract once per session, attach as shared context.
- Pages 3–18: questions 1..26 (typical count). Bold-numbered (1, 2, …). Sub-parts `(a)(b)(c)`. Marks shown as `[N]` per sub-part.
- Pages 19–20: blank/copyright. Skip.
- Diagrams are vector graphics — crop as images and render inline; "NOT TO SCALE" is a label to preserve, not a geometry hint.
- Every page has barcodes + margin instructions — strip during OCR.

**Marking scheme structure (10 pages typical):**
- Pages 1–5: boilerplate (generic marking principles, annotations guide). Skip.
- Pages 6–10: answer table `Question | Answer | Marks | Partial Marks`.
- **`Partial Marks` column is load-bearing**: encodes method-marks (M1/M2/B1/B2) AND valid alternative methods. Conventions: `oe` = "or equivalent", `nfww` = "not from wrong working", `isw` = "ignore subsequent working", `FT` = "follow through". Parse these into per-alternative gate logic for Phase 5 diagnostic feedback.

**Edge cases for answer storage schema:**
- **Graphical answers** (e.g. Q4(a) "mark position B on the diagram") — cannot be auto-marked from a photo reliably. Flag for manual or defer.
- **Multi-choice** (e.g. Q9 "draw a ring around") — MCQ semantics even on otherwise-written paper.
- **Multi-cell table answers** (e.g. Q11, Q23(b)) — answer is an array of cell values, not a scalar. Schema must handle this.
- **LaTeX-required rendering** (e.g. Q26 bold vector notation `m`, `p`) — use MathJax or KaTeX.

## Data model (refined)

- `Syllabus` — code (0580/0654), name, topics[], papers[]
- `Paper` — syllabus_id, number (2/4/6), supports_digital_input (bool — true for 0654 P2)
- `Session` — year, series (F/M / M/J / O/N)
- `PastPaper` — syllabus_id, paper_id, session_id, variant (1/2/3), source_pdf_path, formula_sheet_ref
- `Topic` — syllabus_id, number, name, description
- `Question` — past_paper_id, question_number, topic_id, body_html, images[], marks_total, difficulty, extraction_status (auto / admin_approved / admin_edited)
- `SubPart` — question_id, letter (a/b/c), body_html, answer_schema (scalar / multi_cell / mcq / graphical), correct_answer, canonical_method, marking_alternatives[], marks
- `User` — id, email, password_hash, syllabus_id, learning_style_profile, role (student/admin), cohort_id
- `Cohort` — name, admin_id, visibility_rules
- `Note` — topic_id, content_html, cohort_visibility[]
- `Attempt` — user_id, subpart_id, submitted_answer, working_photo_path, ocr_transcript, verdict (correct_optimal / correct_suboptimal / incorrect), error_tags[], diagnostic_feedback_html, created_at
- `ErrorProfile` — user_id, topic_id, count, weight, last_seen
- `RevisionNote` — user_id, topic_id, generated_content_html, generated_at, style_used, cache_key

## LLM integration

- **Model**: GPT-5.4 (user-specified; verify actual OpenAI availability at Phase 0; fallback list: GPT-5, GPT-4o with vision).
- **API key**: `OPENAI_API_KEY` env var on Railway. Never exposed to client.
- **Rate limits**: per-user per-day caps at the backend. Critical for cost control.
- **Usages**:
  1. Revision-note generation (per user × topic × style).
  2. Handwriting diagnostic evaluation (vision).
  3. Admin-assist question extraction + topic tagging from past-paper PDFs.
  4. Error explanation (conversational, optional).
- **Caching**: revision notes cached per `(user_id, topic_id, style_signature)` — invalidate on significant error-profile delta.

## Phasing (refined with decisions)

- **Phase 0** — ✅ code-complete 2026-04-21. Factory + /health + Alembic scaffold. See `.claude/state/phase-0-plan.md`.
- **Phase 1** — ✅ code-complete 2026-04-21. `Syllabus/Paper/Session/Topic/Note` models, `/syllabus` + `/notes` + `/notes/<id>/partial` HTMX route, seed script for 0580 (7 topics + current recap notes) and 0654 placeholder.
- **Phase 2** — ✅ code-complete 2026-04-21. `User/Cohort` models, pbkdf2 hashing (Werkzeug; no flask-bcrypt needed), `/login` + `/logout`, `admin_required` decorator, `/admin/users` with `secrets.token_urlsafe(16)` issuing and one-shot password display.
- **Phase 3** — ⚠️ scaffold-only 2026-04-21. `PastPaper/Question/SubPart` models, `/admin/papers/upload`, `/admin/review`, `/admin/review/<id>`, extraction service `services/ingestion.py` with `FEATURE_INGESTION` flag. Real PDF→vision call is a TODO (needs `pymupdf` + user validation against mock PDFs). Stub inserts one fake question per upload so review UI works.
- **Phase 4** — ✅ code-complete 2026-04-21. `/exercise` selector, `/exercise/subpart/<id>` renderer, `services/marking.py` for mcq/scalar/multi_cell, `Attempt` persistence, error-profile bump on non-optimal verdicts.
- **Phase 5** — ⚠️ scaffold-only, BLOCKED on prototype gate. `services/ocr.py` diagnose() with `FEATURE_OCR` flag (stub verdict when off), `/attempt/<id>/photo` route, `/prototype/diagnose` endpoint behind `FEATURE_PROTOTYPE`. DO NOT flip `FEATURE_OCR=1` until `.claude/state/phase-5-feasibility.md` reports GREEN (plan.md risk #1).
- **Phase 6** — ✅ code-complete 2026-04-21. 5-question quiz → `learning_style_profile` ∈ {schema_heavy/narrative/formula_first/worked_example}, `/revision` page with per-style LLM note generation behind `FEATURE_REVISION_LLM` (stub when off), `RevisionNote` cache keyed by error-profile snapshot.
- **Phase 7** — ✅ code-complete 2026-04-21. `ErrorProfile` bumps in `/attempt/*` handlers; cache invalidation wired in `/attempt/<id>/photo` (deletes all RevisionNotes for the affected topic).
- **Phase 8** — ✅ partial code-complete 2026-04-21. `RateLimit` table + `bump_and_check` + `@rate_limit` decorator (applied to `/revision` note generation at 50/day). `/admin/cost` dashboard renders per-user daily counters; OpenAI /v1/usage hook is a seam (needs `OPENAI_ADMIN_KEY`). Structured-ish logging in `_configure_logging`. Gunicorn tuning (`--workers 2 --timeout 120`) deferred until vision load observed.

**What still needs user action**:
1. Push the branch + verify Railway deploy boots on the new `Procfile`.
2. `railway run flask --app app db upgrade` once to apply the consolidated migration.
3. `railway run python -m scripts.seed_syllabi` to seed syllabi + current 7 topics into Postgres.
4. Decide whether to create the first admin user via a one-off `railway run` Python snippet (plan doesn't include a bootstrap-admin CLI yet).
5. Collect Phase 5 handwriting corpus → run prototype → commit verdict to `.claude/state/phase-5-feasibility.md` → flip `FEATURE_OCR=1` only after GREEN.
6. Drop mock PDFs into `/data/past-papers/` and flip `FEATURE_INGESTION=1` to pilot Phase 3 extraction.

## Biggest risks

1. **Handwriting evaluation accuracy (Phase 5)** — if GPT vision can't reliably read messy student working, the flagship feature degrades to "input your answer only". **Mitigation**: prototype during Phase 1 on real handwriting samples before committing to Phase 3+.
2. **Past-paper extraction quality (Phase 3)** — bad extraction = corrupted question bank. **Mitigation**: admin review queue required before publish; run Phase 3 pilot on the mock paper first (`mock-question-paper.pdf`, `mock-marking-scheme.pdf` at `/Users/filippomattiamenghi/Downloads/`).
3. **LLM cost** — per-user per-topic note generation + vision calls per attempt can spiral. **Mitigation**: strong caching on revision notes, per-user daily caps, admin-visible cost dashboard in Phase 8.
4. **Scope** — this is multi-month work. **Mitigation**: strict phase gates; `/ultraplan` produces Phase 0 first, then re-plans per phase.

## Non-goals (for now)

- Public signup.
- Payments / subscription.
- Native mobile app (web responsive is enough for classroom tablets/phones).
- Real-time collaboration.
- Discussion / forum features.
- SMTP / email notifications (deferred until credential-issuing flow outgrows admin-paste).
