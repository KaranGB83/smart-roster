"""What-if change handling: apply an availability change to a copy and report the impact."""
from dataclasses import replace
from datetime import date

from .domain import COVERAGE_CODES, Issue, LeaveIn, Problem
from .index import Index
from .suggest import suggest_for_gap
from .validator import validate


def with_leave(problem: Problem, entries: dict, employee_id: str, start: date, end: date,
               kind: str = "leave") -> tuple[Problem, dict]:
    """Return (problem, entries) with the leave added and the affected roster cells set."""
    p2 = replace(problem, leaves=[*problem.leaves, LeaveIn(employee_id, start, end, kind)])
    e2 = dict(entries)
    status = "comp_off" if kind == "comp_off" else "leave"
    for d in Index(problem).days:
        if start <= d <= end:
            e2[(employee_id, d)] = status
    return p2, e2


def impact_of_leave(problem: Problem, entries: dict, employee_id: str, start: date, end: date,
                    kind: str = "leave", suggestions_per_gap: int = 3) -> dict:
    before = validate(problem, entries)
    base_err = {i.key for i in before if i.severity == "error"}
    p2, e2 = with_leave(problem, entries, employee_id, start, end, kind)
    idx = Index(p2)
    after = validate(p2, e2, idx)
    new_gaps = [i for i in after if i.severity == "error" and i.code in COVERAGE_CODES and i.key not in base_err]
    new_other = [i for i in after if i.severity == "error" and i.code not in COVERAGE_CODES
                 and i.key not in base_err]

    # coverage check for every process the person belongs to, on every day of the leave
    checks = []
    for a in idx.asg_by_emp[employee_id]:
        for d in idx.days:
            if start <= d <= end and idx.state(a.bp_id, d) == "open" and idx.required(a.bp_id, d) > 0:
                working = sum(1 for m in idx.members(a.bp_id, d) if e2.get((m, d)) == "working")
                req = idx.required(a.bp_id, d)
                checks.append({"label": idx.bps[a.bp_id].label, "on_date": d, "required": req,
                               "working": working, "ok": working >= req})
    checks.sort(key=lambda c: (c["on_date"], c["label"]))

    gap_reports = [{"issue": g, "suggestions": suggest_for_gap(p2, e2, g.bp_id, g.on_date, suggestions_per_gap)}
                   for g in new_gaps]
    return {"problem": p2, "entries": e2, "issues_after": after, "new_gaps": gap_reports,
            "new_other_errors": new_other, "checks": checks,
            "affected_brands": sorted({g.label.split(" · ")[0] for g in new_gaps}),
            "fully_absorbed": not new_gaps and not new_other}


def diff_issues(before: list[Issue], after: list[Issue]) -> tuple[list[Issue], list[Issue]]:
    """(introduced, resolved) comparing error+warning issues by identity key."""
    b = {i.key: i for i in before if i.severity != "info"}
    a = {i.key: i for i in after if i.severity != "info"}
    return ([a[k] for k in a if k not in b], [b[k] for k in b if k not in a])
