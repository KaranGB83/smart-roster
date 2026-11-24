"""Fix suggestions for a coverage gap. Every candidate is SIMULATED: we apply it to a copy of the
roster, re-run the validator, and only offer it if it closes the gap without creating a new error.
Candidates, best first:
  swap_weekly_off   a colleague on the same process is off that day: they work it, and take their
                    off on another working day of the same week
  borrow_and_swap   same, but the person belongs to another brand/process (temporary assignment)
  double_duty       someone already working elsewhere that day is also assigned to this process
Anything that needs a human decision (backup hire, moving leave, lowering the minimum) is returned
as an 'escalate' suggestion with no automatic edit.
"""
from dataclasses import replace
from datetime import date

from .domain import COVERAGE_CODES, AssignmentIn, Issue, Problem, Suggestion
from .index import Index
from .validator import validate

KIND_RANK = {"swap_weekly_off": 0, "borrow_and_swap": 1, "double_duty": 2}


def _errors(issues: list[Issue]) -> set:
    return {i.key for i in issues if i.severity == "error"}


def suggest_for_gap(problem: Problem, entries: dict, bp_id: str, on_date: date,
                    limit: int = 5, max_sims: int = 160) -> list[Suggestion]:
    idx = Index(problem)
    if bp_id not in idx.bps:
        return []
    label = idx.bps[bp_id].label
    base = validate(problem, entries, idx)
    base_err = _errors(base)
    base_warn = {i.key for i in base if i.severity == "warning"}
    members = set(idx.members(bp_id, on_date))
    iso_week = on_date.isocalendar()[:2]
    week = [d for d in idx.days if d.isocalendar()[:2] == iso_week]

    member_pods = {idx.emps[a.employee_id].pod for a in idx.asg_by_bp[bp_id]} - {None}

    def pod_rank(e) -> int:          # 0 = already on this process, 1 = same pod, 2 = anyone else
        return 0 if e.id in members else (1 if e.pod in member_pods else 2)

    people = sorted(problem.employees, key=lambda e: (pod_rank(e), e.name))
    best: dict[str, Suggestion] = {}
    sims = 0

    for e in people:
        key = (e.id, on_date)
        status = entries.get(key)
        if key in idx.leave or key in problem.locked:
            continue
        is_member = e.id in members
        options: list[tuple[str, list[tuple[date, str]]]] = []
        if status == "working" and not is_member:
            options.append(("double_duty", []))
        elif status == "weekly_off":
            for d2 in week:
                if d2 != on_date and entries.get((e.id, d2)) == "working" and (e.id, d2) not in problem.locked:
                    options.append(("swap_weekly_off" if is_member else "borrow_and_swap",
                                    [(on_date, "working"), (d2, "weekly_off")]))
        for kind, changes in options:
            if sims >= max_sims:
                break
            sims += 1
            new_entries = dict(entries)
            for d, st in changes:
                new_entries[(e.id, d)] = st
            extra = [] if is_member else [AssignmentIn(e.id, bp_id, on_date, on_date)]
            new_problem = replace(problem, assignments=[*problem.assignments, *extra]) if extra else problem
            after = validate(new_problem, new_entries, Index(new_problem) if extra else idx)
            after_err = _errors(after)
            still_open = any(i.severity == "error" and i.bp_id == bp_id and i.on_date == on_date
                             and i.code in COVERAGE_CODES for i in after)
            if still_open or (after_err - base_err):
                continue
            new_warn = [i.message for i in after if i.severity == "warning" and i.key not in base_warn]
            if kind == "swap_weekly_off":
                d2 = changes[1][0]
                title = f"Swap {e.name}'s weekly off: works {on_date:%a %d %b}, off {d2:%a %d %b}"
                detail = f"{e.name} is already on {label}; moving the weekly off keeps weekly-off count intact."
            elif kind == "borrow_and_swap":
                d2 = changes[1][0]
                title = f"Borrow {e.name}: works {on_date:%a %d %b} on {label}, off {d2:%a %d %b}"
                detail = f"{e.name} is not assigned to {label}; adds a one-day assignment for {on_date:%d %b}."
            else:
                other = ", ".join(idx.bps[a.bp_id].label for a in idx.asg_by_emp[e.id]
                                  if a.bp_id != bp_id and idx.state(a.bp_id, on_date) == "open") or "other work"
                title = f"Add {e.name} to {label} on {on_date:%a %d %b} (already working)"
                detail = (f"{e.name} is working {other} that day; covering both doubles their load. "
                          f"Confirm with the pod lead.")
            payload = {
                "entries": [{"employee_id": e.id, "on_date": d.isoformat(), "status": st, "is_locked": True}
                            for d, st in changes],
                "assignments": [{"employee_id": e.id, "brand_process_id": bp_id,
                                 "effective_from": on_date.isoformat(), "effective_to": on_date.isoformat()}
                                for _ in extra],
            }
            sug = Suggestion(kind, title, detail, payload, len(base_err), len(after_err), new_warn[:3])
            old = best.get(e.id)
            sug_rank = (len(new_warn), KIND_RANK[kind], pod_rank(e), len(changes))
            sug.rank = sug_rank
            if old is None or sug_rank < old.rank:
                best[e.id] = sug

    ranked = sorted(best.values(), key=lambda s: (s.rank, s.title))[:limit]
    if not ranked:
        ranked = [Suggestion(
            "escalate", f"No automatic fix for {label} on {on_date:%a %d %b}",
            "Nobody can cover this day without breaking another rule. Options for the manager: assign a "
            "backup resource to this process, ask the employee to move the leave, add a coverage rule "
            "with a lower minimum for the day, or temporarily close the process that day.", None,
            len(base_err), len(base_err))]
    return ranked
