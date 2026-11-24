"""Pure validator / suggestion / change tests (no DB). December 2026: Dec 1 = Tuesday, Sundays 6/13/20/27."""
from datetime import date, timedelta

from app.scheduling.calendar import month_days
from app.scheduling.changes import impact_of_leave
from app.scheduling.domain import AssignmentIn, BrandProcessIn, EmployeeIn, LeaveIn, Problem
from app.scheduling.solver import solve
from app.scheduling.suggest import suggest_for_gap
from app.scheduling.validator import summarize, validate

DEC = date(2026, 12, 1)


def mk(bps, emps, asgs, **kw):
    return Problem(DEC, emps, bps, [AssignmentIn(e, b) for e, b in asgs], **kw)


def bp(id_, cal="sun_holiday_off", mn=1):
    return BrandProcessIn(id_, f"Brand {id_} · CS", cal, frozenset(range(1, 8)), mn)


def codes(issues, sev=None):
    return {i.code for i in issues if sev is None or i.severity == sev}


def solved(p):
    r = solve(p)
    assert r.status in ("optimal", "feasible")
    return dict(r.entries)


def test_solver_output_has_no_errors_when_staffing_allows():
    p = mk([bp("p", "all_365")], [EmployeeIn(x, x) for x in "abc"], [(x, "p") for x in "abc"])
    issues = validate(p, solved(p))
    assert summarize(issues)["publishable"] and not codes(issues, "error")


def test_detects_working_on_leave_and_missing_entries():
    p = mk([bp("p")], [EmployeeIn("e", "Eve")], [("e", "p")],
           leaves=[LeaveIn("e", date(2026, 12, 9), date(2026, 12, 9))])
    entries = solved(p)
    entries[("e", date(2026, 12, 9))] = "working"          # manual edit breaks approved leave
    del entries[("e", date(2026, 12, 20))]
    issues = validate(p, entries)
    assert {"WORKING_ON_LEAVE", "MISSING_ENTRY"} <= codes(issues, "error")
    assert not summarize(issues)["publishable"]


def test_detects_max_consecutive_and_weekly_off_count():
    p = mk([bp("p", "all_365")], [EmployeeIn("e", "Eve")], [("e", "p")])
    entries = {("e", d): "working" for d in month_days(DEC)}  # 31 days straight, no offs
    issues = validate(p, entries)
    assert "MAX_CONSECUTIVE" in codes(issues, "error")
    assert "WEEKLY_OFF_COUNT" in codes(issues, "error")
    only = [i for i in issues if i.code == "MAX_CONSECUTIVE"]
    assert len(only) == 1                                   # reported once per run, not per day


def test_coverage_gap_is_error_and_preference_violation_is_only_warning():
    emps = [EmployeeIn("a", "Ann", preferred_off=frozenset({3})), EmployeeIn("b", "Bob")]
    p = mk([bp("p", "all_365")], emps, [("a", "p"), ("b", "p")])
    entries = solved(p)
    wed = date(2026, 12, 2)
    entries[("a", wed)] = "working"
    entries[("b", wed)] = "working"
    issues = validate(p, entries)
    pref = [i for i in issues if i.code == "PREFERENCE_VIOLATED"]
    assert pref and all(i.severity == "warning" for i in pref)    # a preference can only ever warn
    # ...while the real consequence of cancelling her off (7+ days straight) is a hard error
    assert "MAX_CONSECUTIVE" in codes(issues, "error")
    assert "PREFERENCE_VIOLATED" not in codes(issues, "error")
    entries[("a", wed)] = entries[("b", wed)] = "weekly_off"
    gap = [i for i in validate(p, entries) if i.code == "NO_COVERAGE"]
    assert gap and gap[0].severity == "error" and gap[0].on_date == wed
    assert gap[0].details["staff"] == {"Ann": "weekly_off", "Bob": "weekly_off"}


def test_single_point_of_failure_is_info():
    p = mk([bp("p")], [EmployeeIn("e", "Eve")], [("e", "p")])
    sp = [i for i in validate(p, solved(p)) if i.code == "SINGLE_POINT_OF_FAILURE"]
    assert sp and sp[0].severity == "info" and "Eve" in sp[0].message


def test_suggestion_swaps_colleague_weekly_off_and_is_verified():
    emps = [EmployeeIn(x, x) for x in "abc"]
    p = mk([bp("p", "all_365")], emps, [(x, "p") for x in "abc"])
    entries = solved(p)
    day = date(2026, 12, 9)
    for x in "ab":                                           # two people off together: gap if c is off too
        entries[(x, day)] = "weekly_off"
    entries[("c", day)] = "weekly_off"
    entries[("c", day + timedelta(days=1))] = "working"
    gaps = [i for i in validate(p, entries) if i.code == "NO_COVERAGE" and i.on_date == day]
    assert gaps
    sugs = suggest_for_gap(p, entries, "p", day)
    assert sugs and sugs[0].kind == "swap_weekly_off" and sugs[0].errors_after <= sugs[0].errors_before
    # applying the first suggestion really closes the gap with no new errors
    applied = dict(entries)
    for e in sugs[0].edits["entries"]:
        applied[(e["employee_id"], date.fromisoformat(e["on_date"]))] = e["status"]
    after = validate(p, applied)
    assert not [i for i in after if i.code in ("NO_COVERAGE", "UNDER_MIN_STAFF") and i.on_date == day]


def test_borrow_from_other_brand_and_escalate_when_nobody_can_help():
    emps = [EmployeeIn("a", "Ann"), EmployeeIn("b", "Bob")]
    p = mk([bp("p"), bp("q")], emps, [("a", "p"), ("b", "q")],
           leaves=[LeaveIn("a", date(2026, 12, 9), date(2026, 12, 9))])
    entries = solved(p)
    sugs = suggest_for_gap(p, entries, "p", date(2026, 12, 9))
    assert sugs[0].kind in ("borrow_and_swap", "double_duty")
    assert sugs[0].edits["assignments"][0]["brand_process_id"] == "p"
    # only one employee in the world: no automatic fix, manager escalation with advice
    solo = mk([bp("p")], [EmployeeIn("e", "Eve")], [("e", "p")],
              leaves=[LeaveIn("e", date(2026, 12, 9), date(2026, 12, 9))])
    sugs = suggest_for_gap(solo, solved(solo), "p", date(2026, 12, 9))
    assert [s.kind for s in sugs] == ["escalate"] and sugs[0].edits is None


def test_leave_impact_absorbed_by_team_vs_new_gap():
    emps = [EmployeeIn(x, x) for x in "abc"]
    team = mk([bp("p", "all_365")], emps, [(x, "p") for x in "abc"])
    r = impact_of_leave(team, solved(team), "a", date(2026, 12, 14), date(2026, 12, 15))
    assert r["fully_absorbed"] or r["new_gaps"]             # either is a valid, explained outcome
    solo = mk([bp("p")], [EmployeeIn("e", "Eve")], [("e", "p")])
    r = impact_of_leave(solo, solved(solo), "e", date(2026, 12, 9), date(2026, 12, 9))
    assert not r["fully_absorbed"] and r["affected_brands"] == ["Brand p"]
    assert r["new_gaps"][0]["issue"].on_date == date(2026, 12, 9)
    assert r["new_gaps"][0]["suggestions"][0].kind == "escalate"
    assert any(not c["ok"] for c in r["checks"])
