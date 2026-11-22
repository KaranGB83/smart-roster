# Smart Roster Management System: Design (Stage 1)

## 1. What the assessment really tests
Reliable scheduling and clear conflict detection beat a pretty UI. Everything is driven by
**data, not code**: brands, processes, calendars and rules are rows an ops manager can edit.

## 2. Stack
| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.12), SQLAlchemy/asyncpg or supabase-py, Pydantic v2 |
| Solver | OR-Tools CP-SAT (hard constraints + weighted soft preferences) |
| Frontend | React + Vite + TypeScript, TanStack Query, Tailwind |
| Database | Supabase PostgreSQL |
| Deploy | Backend on Render/Railway (Docker), frontend on Vercel |

## 3. Architecture: modular monolith, microservice-ready
You suggested microservices. For a 4-day, ~2-day-effort assignment I recommend **one deployable
FastAPI app with strictly separated modules**, because separate services add deploy, auth,
networking and demo-failure risk without improving the scheduling quality reviewers grade.
Q7 in the README ("if the company doubled?") is where we explain the path to splitting.

```
backend/app/
  api/            # routers only: thin HTTP layer
  modules/
    directory/    # employees, pods, brands, processes, assignments (CRUD)
    rules/        # calendars, coverage rules, holidays, leaves
    calendar/     # pure functions: is brand_process open on date? who is available?
    solver/       # roster generation (CP-SAT), no DB access, takes/returns plain dataclasses
    validator/    # conflict detection, no DB access, same pure-function style
    changes/      # leave change -> diff -> re-solve unlocked cells -> suggestions
  db/             # session, repositories
```
Rule: modules talk through plain dataclasses, never through each other's tables. `solver` and
`validator` are pure, so they are unit-testable and can be lifted into their own service later
with zero logic changes. If you still want literal separate services, the cleanest split is
`directory+rules` (CRUD API) and `scheduler` (solver+validator+changes).

## 4. Data model (see `supabase/schema.sql`)
- **pods** 1—N **employees** (pod lead is an employee)
- **brands** N—M **processes** through **brand_processes** = *the unit that needs coverage*
  (calendar type, operating days, default min_staff)
- **coverage_rules**: min_staff overrides per weekday or date (sale days)
- **assignments**: employee ↔ brand_process, many per employee (multi-brand/multi-process)
- **holidays**, **leaves** (planned/sick/comp-off, approval status), **shifts**
- **rosters** (versions per month, draft/published, parent_id for regeneration/comparison)
  → **roster_entries** (employee × date × status, `is_manual`, `is_locked`)
- **conflicts** (persisted validation output with ranked suggestions), **audit_log**

**Operating calendar ≠ employee schedule.** `brand_processes.calendar` says when the *client* needs
coverage; `roster_entries` says when each *person* works. Coverage on date *d* for brand process *bp*
= count of assigned employees with `status='working'` on *d*, compared with the required minimum
(0 if closed).

## 5. Solver outline (Stage 3)
Variables: `work[e,d]` boolean. Per-day statuses are derived: forced leave / holiday-off /
comp-off cells are fixed, the rest are working or weekly_off.

**Hard (mandatory)**
1. Approved leave and comp-off ⇒ not working.
2. Locked/manual cells are preserved.
3. Coverage: for each open brand-process day, Σ work over assigned employees ≥ required min.
   An employee on several brand processes counts for all of them that day (documented assumption).
4. Weekly offs: each employee gets exactly `weekly_offs_per_week` (configurable) in each Mon–Sun week.
5. Max consecutive working days.
6. Employees assigned only to closed processes (e.g. Sunday-off) are not rostered on closed days
   unless they have another open assignment.

**Soft (weighted objective)**: preferred off days, fair distribution of weekend/holiday work,
spread of offs within a brand, fewer single-day isolated offs.

**Infeasible?** Don't fail silently. Relax coverage into a slack variable with a heavy penalty,
return the best-effort roster **plus** a conflict list naming the exact brand/process/date and why
(e.g. "Brand X CS, 14 Dec: sole assignee on approved leave").

## 6. Validator outline (Stage 4)
Independent of the solver, so it also checks manual edits. Codes:
`NO_COVERAGE`, `UNDER_MIN_STAFF`, `LEAVE_VS_COVERAGE`, `WEEKLY_OFF_COUNT`, `MAX_CONSECUTIVE`,
`WORKING_ON_LEAVE`, `WORKING_ON_CLOSED_DAY` (warning), `PREFERENCE_VIOLATED` (warning),
`SINGLE_POINT_OF_FAILURE` (info/warning: brand has one resource). Severity: error blocks publish,
warning/info do not.

## 7. Change handling (Stage 4/5)
New leave approved → mark cell → run validator → for every gap, rank candidate fixes:
(1) swap weekly off of a colleague on the same brand, (2) borrow an employee from another brand
with slack (and show the gap it opens elsewhere), (3) comp-off/overtime suggestion, (4) escalate
to manager if none. Optional "re-solve with everything else locked" preserves the published plan.

## 8. Assumptions (to be repeated in README)
- Week = Mon–Sun, default 1 weekly off/week, max 6 consecutive days.
- One shift (10:00–19:00) by default; shifts table exists for extension.
- A person working a day counts toward all their assigned processes that day.
- Public holidays: Maharashtra 2026 list, editable in the UI.
- Leave granularity = full day.

## 9. Stage plan
1. Design + schema (this)
2. FastAPI project, models, CRUD, seed loader skeleton
3. Solver
4. Validator + change handling
5. React dashboard (company / pod / brand / process / employee views, edit + validate)
6. Seed data: 36 employees, 6 pods, ~25 brands (≈80% single-resource), mixed calendars
7. Deploy, README with the 8 questions, demo script

## 10. Repo layout
```
smart-roster/
  backend/   frontend/   supabase/schema.sql   docs/   README.md   .env.example
```
