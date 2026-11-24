"""Roster generation with OR-Tools CP-SAT. Pure: Problem in, Result out.

HARD rules (never broken by the solver)
  - approved leave / comp-off days are not worked; human-locked cells are kept
  - days when none of an employee's processes is open are days off (holiday_off, or weekly_off if
    the closure is part of the weekly pattern, e.g. Sunday for a Sunday-off process)
  - weekly offs: in a full Mon-Sun week with no leave, total weekly offs >= employee.weekly_offs;
    never more than max(weekly_offs, closure days)
  - never more than max_consecutive working days in a row (within the month)
COVERAGE is the one mandatory client requirement we allow to fail, and only visibly: each open
process-day gets a slack variable with a huge penalty, so shortfalls are minimised and then
reported as Gaps with an explanation, instead of the solver silently returning an invalid roster
or just "infeasible".
SOFT (weighted): preferred off weekdays, fair spread of Sunday offs within a team.
"""
import time
from collections import defaultdict
from datetime import date

from ortools.sat.python import cp_model

from .calendar import OPEN, assignment_active, month_days, open_state, required_staff
from .domain import Problem, Result
from .index import Index
from .validator import coverage_gaps

W_GAP, W_PREF, W_FAIR = 1000, 3, 2
OFF_TYPES = {"weekly_off", "holiday_off", "leave", "comp_off"}


def solve(problem: Problem, time_limit: float = 20.0, workers: int = 1, seed: int = 42) -> Result:
    t0 = time.time()
    days = month_days(problem.month_start)
    holidays = problem.holidays
    bps = {b.id: b for b in problem.brand_processes}
    warnings: list[str] = []

    idx = Index(problem)
    asg_by_bp, rules, leave_status = idx.asg_by_bp, idx.rules, idx.leave

    # ---- 1. decide which cells are fixed, which are free decisions
    fixed: dict[tuple[str, date], str] = {}
    for e in problem.employees:
        if not idx.has_any[e.id]:
            warnings.append(f"{e.name} has no active assignment; rostered by weekly-off rules only.")
        for d in days:
            key = (e.id, d)
            if key in leave_status:
                fixed[key] = leave_status[key]
            elif key in problem.locked:
                fixed[key] = problem.locked[key]
            elif idx.forced_off(e.id, d):
                fixed[key] = idx.forced_off(e.id, d)

    model = cp_model.CpModel()
    var = {(e.id, d): model.NewBoolVar(f"w_{e.id}_{d}")
           for e in problem.employees for d in days if (e.id, d) not in fixed}

    def work(eid, d):
        k = (eid, d)
        return var[k] if k in var else (1 if fixed[k] == "working" else 0)

    # ---- 2. weekly offs
    weeks = defaultdict(list)
    for d in days:
        weeks[d.isocalendar()[:2]].append(d)
    for e in problem.employees:
        for wd in weeks.values():
            free = [d for d in wd if (e.id, d) in var]
            if not free:
                continue
            forced_off = sum(1 for d in wd if fixed.get((e.id, d)) == "weekly_off")
            has_leave = any(fixed.get((e.id, d)) in ("leave", "comp_off") for d in wd)
            off_expr = forced_off + len(free) - sum(var[(e.id, d)] for d in free)
            if len(wd) == 7 and not has_leave:
                model.Add(off_expr >= e.weekly_offs)
            model.Add(off_expr <= max(e.weekly_offs, forced_off))

    # ---- 3. max consecutive working days
    for e in problem.employees:
        n = e.max_consecutive
        for i in range(len(days) - n):
            window = [work(e.id, d) for d in days[i:i + n + 1]]
            if any(not isinstance(x, int) for x in window):
                model.Add(sum(window) <= n)

    # ---- 4. coverage with penalised slack
    objective = []
    slots: dict[tuple[str, date], tuple[int, list[str]]] = {}
    for bp in bps.values():
        for d in days:
            if open_state(bp, d, holidays) != OPEN:
                continue
            req = required_staff(bp, d, rules[bp.id])
            if req <= 0:
                continue
            members = [a.employee_id for a in asg_by_bp[bp.id] if assignment_active(a, d)]
            slots[(bp.id, d)] = (req, members)
            slack = model.NewIntVar(0, req, f"gap_{bp.id}_{d}")
            model.Add(sum(work(m, d) for m in members) + slack >= req)
            objective.append(W_GAP * slack)

    # ---- 5. soft preferences
    for e in problem.employees:
        for d in days:
            if (e.id, d) in var and d.isoweekday() in e.preferred_off:
                objective.append(W_PREF * var[(e.id, d)])

    # ---- 6. soft fairness: spread free Sunday offs evenly among people who share a process
    for bp_id, asgs in asg_by_bp.items():
        counts = []
        for eid in {a.employee_id for a in asgs}:
            sundays = [d for d in days if d.isoweekday() == 7 and (eid, d) in var]
            if sundays:
                counts.append(len(sundays) - sum(var[(eid, d)] for d in sundays))
        if len(counts) >= 2:
            hi, lo = model.NewIntVar(0, 6, ""), model.NewIntVar(0, 6, "")
            for c in counts:
                model.Add(hi >= c)
                model.Add(lo <= c)
            objective.append(W_FAIR * (hi - lo))

    model.Minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = seed
    status = solver.Solve(model)

    names = {cp_model.OPTIMAL: "optimal", cp_model.FEASIBLE: "feasible",
             cp_model.INFEASIBLE: "infeasible"}
    res = Result(status=names.get(status, "error"), warnings=warnings,
                 wall_time=round(time.time() - t0, 3), coverage_slots=len(slots))
    if res.status not in ("optimal", "feasible"):
        res.warnings.append("No roster could satisfy the fixed rules (check locked cells, leave "
                            "and max-consecutive-day settings).")
        return res
    res.objective = solver.ObjectiveValue()

    for e in problem.employees:
        for d in days:
            k = (e.id, d)
            res.entries[k] = fixed[k] if k in fixed else (
                "working" if solver.Value(var[k]) else "weekly_off")

    res.gaps, res.coverage_slots = coverage_gaps(problem, res.entries, idx)
    return res
