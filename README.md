# Smart Roster Management System

Monthly roster planning for multi-brand, multi-process operations teams.
FastAPI + PostgreSQL (Supabase) backend, React frontend. Design: [docs/DESIGN.md](docs/DESIGN.md).

> Work in progress. Stages: 1 design/schema ✅ · 2 backend APIs ✅ · 3 solver · 4 validation · 5 dashboard · 6 sample data · 7 deploy.

## Run the backend
1. Create a Supabase project and run `supabase/schema.sql` in the SQL editor.
2. `cp .env.example backend/.env` and set `DATABASE_URL`.
3. ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
4. Open http://localhost:8000/docs for the interactive API.

## Tests
Tests truncate all tables, so use a throwaway Postgres with `schema.sql` applied (not your Supabase project):
```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/roster_test python -m pytest
```

## API overview
CRUD (GET list with `?column=value` filters, POST, GET/PATCH/DELETE `/{id}`):
`/pods` `/employees` `/brands` `/processes` `/brand-processes` `/coverage-rules` `/assignments`
`/holidays` `/leaves` `/shifts`. Plus `/rosters` (+ `/rosters/{id}/entries`), `/assignment-details`, `/health`.
