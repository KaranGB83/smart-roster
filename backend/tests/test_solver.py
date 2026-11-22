"""Pure solver tests (no DB use). December 2026: Dec 1 is Tuesday, Dec 6/13/20/27 are Sundays."""
from datetime import date

from app.scheduling.domain import (AssignmentIn, BrandProcessIn, CoverageRuleIn, EmployeeIn, LeaveIn,
                                   Problem)
from app.scheduling.solver import solve

DEC = date(2026, 12, 1)


def prob(bps, emps, asgs, **kw):
    return Problem(DEC, emps, bps, [AssignmentIn(e, b) for e, b in asgs], **kw)


def bp(id_, cal, mn=1, days=None):
    return BrandProcessIn(id_, f"Brand {id_}", cal, frozenset(days or range(1, 8)), mn)


def offs(res, eid):
    return sorted(d for (e, d), s in res.entries.items() if e == eid and s != "working")


def test_sole_resource_mon_sat_gets_sundays_off_and_no_gaps():
    res = solve(prob([bp("b", "sun_holiday_off")], [EmployeeIn("e", "Eve")], [("e", "b")]))
    assert res.status == "optimal" and not res.gaps
    assert offs(res, "e") == [date(2026, 12, d) for d in (6, 13, 20, 27)]


def test_two_people_cover_365_by_staggering_offs():
    emps = [EmployeeIn("a", "Ann"), EmployeeIn("b", "Bob")]
    res = solve(prob([bp("p", "all_365")], emps, [("a", "p"), ("b", "p")]))
    assert not res.gaps
    assert not set(offs(res, "a")) & set(offs(res, "b"))      # never off together
    assert len(offs(res, "a")) >= 4 and len(offs(res, "b")) >= 4


def test_sole_resource_on_365_is_flagged_not_hidden():
    res = solve(prob([bp("p", "all_365")], [EmployeeIn("a", "Ann")], [("a", "p")]))
    assert res.status in ("optimal", "feasible")
    assert len(res.gaps) >= 4                                  # one weekly off per week => gap
    assert {g.code for g in res.gaps} == {"NO_COVERAGE"}
    assert {g.cause for g in res.gaps} == {"weekly_off_limits"}
    assert all("Ann" in g.staff for g in res.gaps)


def test_leave_of_sole_resource_creates_explained_gap():
    leave = LeaveIn("e", date(2026, 12, 9), date(2026, 12, 9))
    res = solve(prob([bp("b", "sun_holiday_off")], [EmployeeIn("e", "Eve")], [("e", "b")],
                     leaves=[leave]))
    assert [g.on_date for g in res.gaps] == [date(2026, 12, 9)]
    g = res.gaps[0]
    assert g.code == "NO_COVERAGE" and g.cause == "unavailable_staff" and g.staff == {"Eve": "leave"}
    assert "Brand b" in g.message and "Wed 09 Dec" in g.message


def test_three_person_team_absorbs_one_absence():
    emps = [EmployeeIn(x, x) for x in "abc"]
    leave = LeaveIn("a", date(2026, 12, 7), date(2026, 12, 11))
    res = solve(prob([bp("p", "all_365")], emps, [(x, "p") for x in "abc"], leaves=[leave]))
    assert not res.gaps
    assert all(res.entries[("a", date(2026, 12, d))] == "leave" for d in range(7, 12))


def test_public_holiday_closes_process_without_gap():
    hol = {date(2026, 12, 9): "Sample holiday"}
    res = solve(prob([bp("b", "sun_holiday_off")], [EmployeeIn("e", "Eve")], [("e", "b")],
                     holidays=hol))
    assert not res.gaps
    assert res.entries[("e", date(2026, 12, 9))] == "holiday_off"
    assert res.entries[("e", date(2026, 12, 6))] == "weekly_off"      # Sunday still the weekly off


def test_holiday_on_365_process_is_still_worked():
    hol = {date(2026, 12, 25): "Christmas"}
    emps = [EmployeeIn("a", "Ann"), EmployeeIn("b", "Bob")]
    res = solve(prob([bp("p", "all_365")], emps, [("a", "p"), ("b", "p")], holidays=hol))
    assert not res.gaps
    assert "working" in (res.entries[("a", date(2026, 12, 25))], res.entries[("b", date(2026, 12, 25))])


def test_weekday_and_date_coverage_rules():
    emps = [EmployeeIn(x, x) for x in "abc"]
    rules = [CoverageRuleIn("p", 2, day_of_week=6), CoverageRuleIn("p", 3, on_date=date(2026, 12, 12))]
    res = solve(prob([bp("p", "all_365")], emps, [(x, "p") for x in "abc"], coverage_rules=rules))
    assert not res.gaps
    work = lambda d: sum(res.entries[(x, d)] == "working" for x in "abc")  # noqa: E731
    assert work(date(2026, 12, 12)) == 3                      # date rule beats Saturday rule
    assert work(date(2026, 12, 19)) >= 2 and work(date(2026, 12, 26)) >= 2


def test_preference_is_honoured_when_coverage_allows_and_ignored_when_it_does_not():
    emps = [EmployeeIn("a", "Ann", preferred_off=frozenset({7})), EmployeeIn("b", "Bob")]
    res = solve(prob([bp("p", "all_365")], emps, [("a", "p"), ("b", "p")]))
    assert all(date(2026, 12, d) in offs(res, "a") for d in (6, 13, 20, 27))
    # both want Sunday off but coverage is mandatory: preference loses, no gap
    emps = [EmployeeIn(x, x, preferred_off=frozenset({7})) for x in "ab"]
    res = solve(prob([bp("p", "all_365")], emps, [(x, "p") for x in "ab"]))
    assert not res.gaps
    for d in (6, 13, 20, 27):
        assert "working" in (res.entries[("a", date(2026, 12, d))], res.entries[("b", date(2026, 12, d))])


def test_locked_cells_are_kept():
    emps = [EmployeeIn("a", "Ann"), EmployeeIn("b", "Bob")]
    locked = {("a", date(2026, 12, 9)): "weekly_off"}
    res = solve(prob([bp("p", "all_365")], emps, [("a", "p"), ("b", "p")], locked=locked))
    assert res.entries[("a", date(2026, 12, 9))] == "weekly_off"
    assert res.entries[("b", date(2026, 12, 9))] == "working" and not res.gaps


def test_max_consecutive_days_respected():
    emps = [EmployeeIn(x, x, max_consecutive=5) for x in "abc"]
    res = solve(prob([bp("p", "all_365")], emps, [(x, "p") for x in "abc"]))
    days = sorted({d for (_, d) in res.entries})
    for x in "abc":
        run = 0
        for d in days:
            run = run + 1 if res.entries[(x, d)] == "working" else 0
            assert run <= 5


def test_employee_working_two_brands_counts_for_both_and_unassigned_is_warned():
    emps = [EmployeeIn("a", "Ann"), EmployeeIn("z", "Zed")]
    res = solve(prob([bp("p", "sun_holiday_off"), bp("q", "sun_holiday_off")], emps,
                     [("a", "p"), ("a", "q")]))
    assert not res.gaps
    assert any("Zed" in w for w in res.warnings)
