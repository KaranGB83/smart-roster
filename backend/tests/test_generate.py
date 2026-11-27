"""End-to-end: seed -> generate -> independent validity check -> change -> regenerate."""
from collections import defaultdict
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.seed import seed


@pytest.fixture()
def seeded(client):
    with Session(get_engine()) as db:
        info = seed(db)
    assert info == {"employees": 36, "pods": 6, "brands": 30, "brand_processes": 56}
    return client


def generate(client, **kw):
    r = client.post("/rosters/generate", json={"month_start": "2026-12-01", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_seed_shape_matches_brief(seeded):
    rows = seeded.get("/assignment-details").json()
    primary_by_brand = defaultdict(set)
    for r in rows:
        primary_by_brand[r["brand"]].add(r["employee_id"])
    assert len(seeded.get("/employees").json()) == 36
    # 24 of 30 brands (80%) have exactly one resource
    assert sum(1 for s in primary_by_brand.values() if len(s) == 1) == 24


def test_december_baseline_is_clean_and_valid(seeded):
    out = generate(seeded)
    assert out["solver_status"] in ("optimal", "feasible")
    assert out["gap_count"] == 0 and out["coverage_slots"] > 1000
    entries = seeded.get(f"/rosters/{out['roster']['id']}/entries").json()
    assert len(entries) == 36 * 31
    emps = {e["id"]: e for e in seeded.get("/employees").json()}
    by_emp = defaultdict(dict)
    for en in entries:
        by_emp[en["employee_id"]][date.fromisoformat(en["on_date"])] = en["status"]
    for eid, cal in by_emp.items():
        run, ordered = 0, sorted(cal)
        for d in ordered:
            run = run + 1 if cal[d] == "working" else 0
            assert run <= emps[eid]["max_consecutive_days"], (emps[eid]["full_name"], d)
        # full Mon-Sun weeks without leave have at least the contractual weekly offs
        weeks = defaultdict(list)
        for d in ordered:
            weeks[d.isocalendar()[:2]].append(d)
        for wd in weeks.values():
            statuses = [cal[d] for d in wd]
            if len(wd) == 7 and not {"leave", "comp_off"} & set(statuses):
                assert statuses.count("weekly_off") >= emps[eid]["weekly_offs_per_week"]
    # approved leave of employee 26 (Dec 14-15) is respected
    e26 = next(e for e in emps.values() if e["code"] == "EMP-026")["id"]
    assert by_emp[e26][date(2026, 12, 14)] == "leave" and by_emp[e26][date(2026, 12, 15)] == "leave"


def test_pending_leave_is_ignored_until_approved_then_gap_is_flagged(seeded):
    assert generate(seeded)["gap_count"] == 0                  # pending leave for EMP-005 ignored
    pending = next(lv for lv in seeded.get("/leaves").json() if lv["status"] == "pending")
    assert seeded.patch(f"/leaves/{pending['id']}", json={"status": "approved"}).status_code == 200
    out = generate(seeded, name="After leave approval")
    assert out["gap_count"] == 1
    g = out["gaps"][0]
    assert g["label"] == "EcoNest · CS" and g["on_date"] == "2026-12-09"
    assert g["code"] == "NO_COVERAGE" and g["cause"] == "unavailable_staff"
    assert g["staff"] == {"Kabir Singh": "leave"}
    # persisted as a conflict on the roster for the manager to work through
    stored = seeded.get("/conflicts", params={"roster_id": out["roster"]["id"]}).json()
    errors = [c for c in stored if c["severity"] == "error"]
    assert len(errors) == 1 and errors[0]["code"] == "NO_COVERAGE" and not errors[0]["resolved"]


def test_regeneration_keeps_locked_cells(seeded):
    first = generate(seeded)
    rid = first["roster"]["id"]
    emp = next(e for e in seeded.get("/employees").json() if e["code"] == "EMP-025")
    seeded.put(f"/rosters/{rid}/entries", json=[
        {"employee_id": emp["id"], "on_date": "2026-12-10", "status": "weekly_off", "is_locked": True}])
    second = generate(seeded, name="Regenerated", base_roster_id=rid)
    assert second["gap_count"] == 0
    cells = seeded.get(f"/rosters/{second['roster']['id']}/entries",
                       params={"employee_id": emp["id"], "date_from": "2026-12-10",
                               "date_to": "2026-12-10"}).json()
    assert cells[0]["status"] == "weekly_off" and cells[0]["is_locked"] and cells[0]["is_manual"]
    assert second["roster"]["parent_id"] == rid
