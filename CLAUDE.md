# IGCSE 0580 Recap Map

Classroom-ready revision site for Cambridge IGCSE 0580 Mathematics. Currently a static single-page app covering 7 topics; being scaled for in-class use. Current roadmap lives in `.claude/state/plan.md`.

## Live URL

- **Production**: https://igcse.menghi.dev (Cloudflare tunnel → local Flask on :5000)
- **Exam date displayed on the page**: 29 Apr 2026

## Run locally

```bash
pip install flask
python app.py
# → http://localhost:5000
```

`app.py` serves the project folder as the static root (`static_folder='.'`, `static_url_path=''`), so `index.html`, `css/`, and `js/` all load from `/`.

## Deployment ladder

1. **Now** — local Flask + Cloudflare tunnel to `igcse.menghi.dev`. Tied to the dev machine being awake.
2. **Next** — Railway for the Flask backend, once server-side state is needed for classroom features.
3. **Fallback** — Vercel for the frontend only, if a frontend/backend split becomes necessary.

**Invariant**: the app must remain runnable locally (`python app.py`) through every stage. Do not introduce dependencies that require cloud-only services for the dev loop.

## File inventory

| File | Purpose |
|------|---------|
| `index.html` | Single page. Header → summary grid → topic filter nav → 7 `<article class="topic-card" data-id="N">` blocks → strategy footer. All content is hand-written HTML. |
| `css/style.css` | All styling. Design tokens are CSS custom properties under `:root` (light) and `body.dark-mode` (dark). Claude-widget aesthetic. Includes print styles that hide nav + force all cards visible. |
| `js/app.js` | Vanilla JS IIFE. Three responsibilities: topic filter (click `.nav-btn`, toggle `.hidden` on cards), dark-mode toggle persisted in `localStorage` under key `igcse-theme`, keyboard shortcuts. |
| `app.py` | 10-line Flask dev server. No API yet. |
| `README.md` | User-facing readme for the static site (pre-dates Flask — tells readers they can just open `index.html`). |

## File relationships (change-one-affects-another)

- **Adding a new topic**: edit `index.html` in two places — add an `<article class="topic-card" data-id="N">` and a matching `<button class="nav-btn" data-topic="N">` in `.topic-nav`. The filter in `js/app.js` picks up new cards automatically via `querySelectorAll('.topic-card')`, BUT the keyboard shortcuts only accept keys `1`–`7` (see `js/app.js:72`). Extend that range when adding topic 8+.
- **Theme**: any new component must use `var(--color-...)` tokens defined in `css/style.css:7-36` and `:40-61`. Hard-coded colours will break dark mode.
- **Topic accent colours**: 7 colour classes (`.color-purple`, `.color-teal`, …) at `css/style.css:234-248` have light + dark variants. Adding an 8th topic means adding a new class *and* its `body.dark-mode` override.
- **Adding an API later**: `app.py` currently uses `static_url_path=''`, which serves every file from `/`. Before introducing routed endpoints, either move statics under `/static/` or switch to a Blueprint — otherwise API routes will collide with filenames at the root.

## Project internal state files

Under `.claude/state/`:

- `plan.md` — current roadmap for scaling; fixed constraints; hosting decisions.
- `todo.md` — outstanding tasks across sessions (distinct from per-turn TodoWrite lists).
- `abbreviations.md` — project-specific shorthand for internal notes.

Read these at session start. Update them when scope changes. They are the source of truth — if in-chat memory disagrees, the file wins.

## Not yet decided

- Backend DB (none yet — candidates: SQLite on Railway volume, Postgres).
- Auth model (student accounts vs. per-class codes vs. anonymous with device-ID).
- Monolithic Flask vs. split (Flask API on Railway + static frontend on Vercel).

Once these are decided, capture the decision + rationale in `.claude/state/plan.md`.
