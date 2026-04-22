"""Local-only ingestion pipeline for CAIE past papers.

Runs on the dev machine (not Railway) because:
- Vision-free extraction (pdfplumber + rules) is deterministic but iterative
  to tune — fast local loops beat Railway redeploys.
- Images are cropped from PDF pages and need the raw PDFs, which live on
  the dev machine.
- Database writes go directly to Railway Postgres via DATABASE_URL (the
  TCP proxy works from anywhere), so there's no "migration" step — the
  rows this produces ARE the production rows.

After the run completes, local_ingest/images/ gets zipped and uploaded
to the Railway volume via /admin/images/upload — a one-time step.
"""
