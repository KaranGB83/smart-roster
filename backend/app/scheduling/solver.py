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

from .calendar import (CLOSED_HOLIDAY, OPEN, assignment_active, month_days, open_state,
                       required_staff)
from .domain import Gap, Problem, Result

W_GAP, W_PREF, W_FAIR = 1000, 3, 2
OFF_TYPES = {"weekly_off", "holiday_off", "leave", "comp_off"}


def solve(problem: Problem, time_limit: float = 20.0, workers: int = 1, seed: int = 42) -> Result:
    t0 = time.time()
    days = month_days(problem.month_start)
    holidays = problem.holidays
    emps = {e.id: e for e in problem.employees}
    bps = {b.id: b for b in problem.brand_processes}
    warnings: list[str] = []

    asg_by_emp = defaultdict(list)
    asg_by_bp = defaultdict(list)
    for a in problem.assignments:
        if a.employee_id in emps and a.bp_id in bps:
            asg_by_emp[a.employee_id].append(a)
            asg_by_bp[a.bp_id].append(a)
    rules = defaultdict(list)
    for r in problem.coverage_rules:
        rules[r.bp_id].append(r)

    leave_status: dict[tuple[str, date], str] = {}
    for lv in problem.leaves:
        if lv.employee_id not in emps:
            continue
        for d in days:
            if lv.start <= d <= lv.end:
                leave_status[(lv.employee_id, d)] = "comp_off" if lv.kind == "comp_off" else "leave"

    # ---- 1. decide which cells are fixed, which are free decisions
    fixed: dict[tuple[str, date], str] = {}
    for e in problem.employees:
        has_any = any(assignment_active(a, d) for a in asg_by_emp[e.id] for d in days)
        if not has_any:
            warnings.append(f"{e.name} has no active assignment; rostered by weekly-off rules only.")
        for d in days:
            key = (e.id, d)
            if key in leave_status:
                fixed[key] = leave_status[key]
            elif key in problem.locked:
                fixed[key] = problem.locked[key]
            elif has_any:
                states = [open_state(bps[a.bp_id], d, holidays)
                          for a in asg_by_emp[e.id] if assignment_active(a, d)]
                if OPEN not in states:
                    fixed[key] = "holiday_off" if CLOSED_HOLIDAY in states else "weekly_off"

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

    res.gaps = _find_gaps(problem, slots, res.entries, fixed, emps, bps)
    return res


def _find_gaps(problem, slots, entries, fixed, emps, bps) -> list[Gap]:
    """Re-derive coverage from the final entries (independent of solver internals)."""
    gaps = []
    for (bp_id, d), (req, members) in sorted(slots.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        covered = sum(1 for m in members if entries[(m, d)] == "working")
        if covered >= req:
            continue
        capacity = sum(1 for m in members if fixed.get((m, d), "working") == "working")
        cause = "unavailable_staff" if capacity < req else "weekly_off_limits"
        staff = {emps[m].name: entries[(m, d)] for m in members}
        label = bps[bp_id].label
        if not members:
            hint = "No employee is assigned to this process."
        elif cause == "unavailable_staff":
            hint = ("Not enough people are available (leave / comp-off / closed days): "
                    "add a backup assignment, move someone's leave, or reduce the minimum.")
        else:
            hint = ("Enough people are available, but weekly-off and consecutive-day limits "
                    "leave this day short: add another resource or relax a weekly off.")
        gaps.append(Gap(
            bp_id=bp_id, label=label, on_date=d, required=req, covered=covered,
            code="NO_COVERAGE" if covered == 0 else "UNDER_MIN_STAFF", cause=cause,
            message=f"{label} on {d:%a %d %b}: needs {req}, has {covered}. {hint}",
            staff=staff))
    return gaps
