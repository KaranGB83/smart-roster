# Smart Roster Management System

Monthly roster planning for multi-brand, multi-process operations teams.
FastAPI + PostgreSQL (Supabase) backend, React frontend. Design: [docs/DESIGN.md](docs/DESIGN.md).

> Work in progress. Stages: 1 design/schema ✅ · 2 backend APIs ✅ · 3 roster solver ✅ · 4 validation/changes · 5 dashboard · 6 sample data (seed ✅, to refine) · 7 deploy.

## Run the backend
1. Create a Supabase project and run `supabase/schema.sql` in the SQL editor.
2. `cp .env.example backend/.env` and set `DATABASE_URL`.
3. ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
4. Load the sample data (36 employees, 6 pods, 25 brands; **wipes all tables**): `python -m app.seed --reset`
5. Open http://localhost:8000/docs for the interactive API, then try
   `POST /rosters/generate {"month_start": "2026-12-01"}`.

## Tests
Tests truncate all tables, so use a throwaway Postgres with `schema.sql` applied (not your Supabase project):
```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/roster_test python -m pytest
```

## API overview
CRUD (GET list with `?column=value` filters, POST, GET/PATCH/DELETE `/{id}`):
`/pods` `/employees` `/brands` `/processes` `/brand-processes` `/coverage-rules` `/assignments`
`/holidays` `/leaves` `/shifts`. Plus `/rosters` (+ `/rosters/{id}/entries`), `/assignment-details`, `/health`.

## Roster generation (Stage 3)
`POST /rosters/generate` builds a draft roster with OR-Tools CP-SAT (`app/scheduling/solver.py`, pure
Python, no DB access). It never silently returns an invalid roster:
- **Hard rules:** approved leave/comp-off, locked cells, weekly offs, max consecutive days, closed
  days (holiday / Sunday-off / custom calendars).
- **Coverage:** minimum staff per brand-process-day is penalised, not assumed. Any shortfall comes
  back as a gap with a cause (`unavailable_staff` vs `weekly_off_limits`) and the status of every
  assigned person that day; gaps are also stored in `conflicts` (`GET /conflicts?roster_id=`).
- **Soft rules:** preferred off weekdays, fair spread of Sunday offs inside a team.
- **Regeneration:** pass `base_roster_id` to keep that roster's locked cells fixed.
- Only **approved** leave blocks a person; pending/rejected leave is ignored.

Assumptions: week = Mon-Sun; one person working counts toward every process they are assigned to that
day; `custom` calendars are closed on public holidays; the month is solved on its own (no carry-over
of consecutive days from the previous month).
