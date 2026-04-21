# IGCSE 0580 Recap — TODO

## Pre-Phase-0 (this session)

- [x] `git init` + `.gitignore` + initial commit + push to `github.com/Cyberfilo/Smart-igcse-platform` — 2026-04-21
- [ ] User: create Railway project linked to GitHub repo (see `RAILWAY.md`)
- [ ] User: add Postgres service to Railway project
- [ ] User: add Volume to Railway project (mount `/data`)
- [ ] User: set env vars — `OPENAI_API_KEY`, `SECRET_KEY` (random 32+ bytes)
- [ ] User: in Cloudflare, swap `igcse.menghi.dev` record from tunnel → CNAME to Railway service domain
- [ ] Run `/ultraplan` on the repo (now git-initialised) to produce Phase 0 detailed plan
- [ ] Confirm actual GPT model available at build time (user said GPT-5.4 — fallback: GPT-5, GPT-4o vision)

## Phase 3 pilot input

- [ ] Copy `/Users/filippomattiamenghi/Downloads/mock-question-paper.pdf` + `mock-marking-scheme.pdf` into `pilot-data/` in the repo (gitignored if large; else tracked) for the extraction pilot once Phase 3 begins

## Done — Session 2026-04-21

- [x] Created `CLAUDE.md`, `.claude/state/plan.md`, `todo.md`, `abbreviations.md`
- [x] Captured full feature spec (SaveMyExams-style platform, 3 pages, admin, multi-syllabus, personalised revision, handwriting OCR)
- [x] Resolved 9 architecture decisions (see `plan.md` → Architecture decisions)
- [x] Dropped local-run constraint; Railway-only hosting
- [x] Analysed mock PDFs (`0580/43` October/November 2025 + mark scheme) → extraction notes in `plan.md`

## Format

- Each item: `- [ ] <verb> <object> — <why / where>`
- Completed items move to `## Done — Session <date>` with date.
- Items blocked on a decision go under `## Blocked` with the blocker named.
