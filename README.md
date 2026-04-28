# Smart IGCSE Platform

Personal exam-prep platform I built for myself to study for Cambridge IGCSE 0580 (Mathematics) and 0654 (Coordinated Sciences). Past papers, notes, revision pages, and exercise sheets — pulled into a single Flask app with hybrid LLM-powered ingestion.

I wrote this because the official Cambridge resources are scattered across PDFs, the unofficial revision sites are inconsistent in quality, and I needed a single navigable surface for my own studying. It's deployed on Railway with a 200GB Postgres volume.

## Features

- **Unified past-paper viewer** — papers from multiple sessions and variants, normalized into a consistent structure
- **Notes pages** — topic-organized for both syllabi
- **Revision summaries** — generated and curated from the source material
- **Exercise pages** — interactive practice with worked answers
- **Hybrid ingestion worker** — OpenAI-powered: chunks PDFs, extracts structured content, writes to Postgres directly
- **Railway-native** — branch-tied environments, 200GB volume for storage of paper PDFs and extracted assets

## Stack

- **Backend**: Python 3, Flask, SQLAlchemy
- **Database**: PostgreSQL (with a 200GB Railway volume for asset storage)
- **AI**: OpenAI API for ingestion + content normalization
- **Hosting**: Railway (auto-deploy from `staging` and `main` branches)
- **Frontend**: server-rendered HTML + CSS (kept lean — this is a study tool, not a SaaS)

## Architecture

```
┌─────────────────────────────┐
│  Source PDFs / past papers  │
└──────────────┬──────────────┘
               │
               ▼
   ┌───────────────────────┐
   │  Ingestion worker     │  ← OpenAI for chunk parsing, structure extraction
   │  (Python, batch)      │
   └──────────┬────────────┘
              │
              ▼
   ┌───────────────────────┐
   │  PostgreSQL           │  ← normalized: subjects, topics, papers, questions
   │  (Railway volume)     │
   └──────────┬────────────┘
              │
              ▼
   ┌───────────────────────┐
   │  Flask app            │  ← server-rendered, lean UI
   └──────────┬────────────┘
              │
              ▼
   ┌───────────────────────┐
   │  My iPad in the morning │
   └─────────────────────────┘
```

## Running locally

```bash
git clone https://github.com/Cyberfilo/Smart-igcse-platform.git
cd Smart-igcse-platform

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in: DATABASE_URL, OPENAI_API_KEY

python app.py
# Visit http://localhost:5000
```

## Deployment

Railway connects directly to this repo. Pushing to `staging` deploys to the staging environment; `main` deploys to production. The Postgres database is a Railway service with a 200GB volume attached.

## Status

Active. I use this daily during exam prep. The ingestion worker has run through both syllabi end-to-end; current work is on the revision-page UX and the exercise interactivity.

## License

MIT.

## Notes

This is a tool I built for myself first. If you're a Cambridge IGCSE student and want to adapt it for your own use, the code is open — the source data (past papers, syllabi) is property of Cambridge International and is not included in this repo.
