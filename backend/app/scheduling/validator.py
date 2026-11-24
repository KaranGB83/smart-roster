"""Roster validation. Pure and independent of the solver, so it also checks manual edits.

Mandatory (severity=error, blocks publishing):
  NO_COVERAGE / UNDER_MIN_STAFF, WORKING_ON_LEAVE, WEEKLY_OFF_COUNT, MAX_CONSECUTIVE, MISSING_ENTRY
Soft (warning):  WORKING_ON_CLOSED_DAY, EXTRA_WEEKLY_OFF, PREFERENCE_VIOLATED
Informational:   SINGLE_POINT_OF_FAILURE
A required client coverage day always outranks a preference: preferences can only ever warn.
"""
from collections import defaultdict
from datetime import date

from .calendar import OPEN, assignment_active
from .domain import Gap, Issue, Problem
from .index import Index

WD = "Mon Tue Wed Thu Fri Sat Sun".split()
SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


def coverage_gaps(problem: Problem, entries: dict, idx: Index | None = None) -> tuple[list[Gap], int]:
    idx = idx or Index(problem)
    gaps: list[Gap] = []
    slots = 0
    for bp_id, bp in idx.bps.items():
        for d in idx.days:
            if idx.state(bp_id, d) != OPEN:
                continue
            req = idx.required(bp_id, d)
            if req <= 0:
                continue
            slots += 1
            members = idx.members(bp_id, d)
            covered = sum(1 for m in members if entries.get((m, d)) == "working")
            if covered >= req:
                continue
            on_leave = [m for m in members if (m, d) in idx.leave]
            if len(members) - len(on_leave) < req:
                cause = "unavailable_staff"
            elif any(problem.locked.get((m, d)) not in (None, "working") for m in members):
                cause = "locked_cells"
            else:
                cause = "weekly_off_limits"
            hint = {
                "unavailable_staff": ("Not enough people are available (leave / comp-off): add a backup "
                                      "assignment, move someone's leave, or lower the minimum."),
                "locked_cells": "A locked day-off blocks coverage: unlock it or swap with a colleague.",
                "weekly_off_limits": ("Enough people are available but weekly offs / consecutive-day limits "
                                      "leave this day short: swap a weekly off or add a resource."),
            }[cause]
            if not members:
                hint = "No employee is assigned to this process."
            staff = {idx.emps[m].name: entries.get((m, d), "missing") for m in members}
            gaps.append(Gap(
                bp_id=bp_id, label=bp.label, on_date=d, required=req, covered=covered,
                code="NO_COVERAGE" if covered == 0 else "UNDER_MIN_STAFF", cause=cause,
                message=f"{bp.label} on {d:%a %d %b}: needs {req}, has {covered}. {hint}", staff=staff))
    gaps.sort(key=lambda g: (g.on_date, g.label))
    return gaps, slots


def validate(problem: Problem, entries: dict, idx: Index | None = None) -> list[Issue]:
    idx = idx or Index(problem)
    issues: list[Issue] = []
    gaps, _ = coverage_gaps(problem, entries, idx)
    for g in gaps:
        issues.append(Issue(g.code, "error", g.message, g.on_date, g.bp_id, None, g.label,
                            {"required": g.required, "covered": g.covered, "cause": g.cause,
                             "staff": g.staff}))

    weeks = defaultdict(list)
    for d in idx.days:
        weeks[d.isocalendar()[:2]].append(d)

    for e in problem.employees:
        name = e.name
        missing = [d for d in idx.days if (e.id, d) not in entries]
        if missing:
            issues.append(Issue("MISSING_ENTRY", "error",
                                f"{name} has no roster entry for {len(missing)} day(s), first {missing[0]:%d %b}.",
                                missing[0], None, e.id, None, {"count": len(missing)}))
        run = 0
        for d in idx.days:
            st = entries.get((e.id, d))
            if st == "working" and (e.id, d) in idx.leave:
                issues.append(Issue("WORKING_ON_LEAVE", "error",
                                    f"{name} is rostered to work on {d:%a %d %b} but has approved "
                                    f"{idx.leave[(e.id, d)].replace('_', '-')}.", d, None, e.id))
            if st == "working" and idx.forced_off(e.id, d):
                issues.append(Issue("WORKING_ON_CLOSED_DAY", "warning",
                                    f"{name} works {d:%a %d %b} but none of their processes is open.",
                                    d, None, e.id))
            run = run + 1 if st == "working" else 0
            if run == e.max_consecutive + 1:
                issues.append(Issue("MAX_CONSECUTIVE", "error",
                                    f"{name} works more than {e.max_consecutive} days in a row "
                                    f"(exceeds on {d:%a %d %b}).", d, None, e.id))
        for wd in weeks.values():
            statuses = [entries.get((e.id, d)) for d in wd]
            wo = statuses.count("weekly_off")
            forced = sum(1 for d in wd if idx.forced_off(e.id, d) == "weekly_off")
            has_leave = any((e.id, d) in idx.leave or s in ("leave", "comp_off")
                            for d, s in zip(wd, statuses))
            if len(wd) == 7 and not has_leave and None not in statuses and wo < e.weekly_offs:
                issues.append(Issue("WEEKLY_OFF_COUNT", "error",
                                    f"{name} has {wo} weekly off(s) in the week of {wd[0]:%d %b}; "
                                    f"needs {e.weekly_offs}.", wd[0], None, e.id))
            elif wo > max(e.weekly_offs, forced):
                issues.append(Issue("EXTRA_WEEKLY_OFF", "warning",
                                    f"{name} has {wo} weekly offs in the week of {wd[0]:%d %b} "
                                    f"(entitled to {max(e.weekly_offs, forced)}): reduces capacity.",
                                    wd[0], None, e.id))
        if e.preferred_off:
            pref_days = [d for d in idx.days if d.isoweekday() in e.preferred_off]
            worked = [d for d in pref_days if entries.get((e.id, d)) == "working"]
            if worked:
                dn = "/".join(WD[x - 1] for x in sorted(e.preferred_off))
                issues.append(Issue("PREFERENCE_VIOLATED", "warning",
                                    f"{name} works {len(worked)} of {len(pref_days)} preferred off days "
                                    f"({dn}); coverage or calendar rules took priority.",
                                    None, None, e.id, None, {"worked": len(worked), "of": len(pref_days)}))

    for bp_id, bp in idx.bps.items():
        people = {a.employee_id for a in idx.asg_by_bp[bp_id] if any(assignment_active(a, d) for d in idx.days)}
        if len(people) == 1 and any(idx.state(bp_id, d) == OPEN for d in idx.days):
            only = idx.emps[next(iter(people))].name
            issues.append(Issue("SINGLE_POINT_OF_FAILURE", "info",
                                f"{bp.label} depends on one person ({only}); any absence creates a gap.",
                                None, bp_id, next(iter(people)), bp.label))

    issues.sort(key=lambda i: (SEV_ORDER[i.severity], i.on_date or date.max, i.code))
    return issues


def summarize(issues: list[Issue]) -> dict:
    return {"errors": sum(i.severity == "error" for i in issues),
            "warnings": sum(i.severity == "warning" for i in issues),
            "info": sum(i.severity == "info" for i in issues),
            "publishable": not any(i.severity == "error" for i in issues)}
