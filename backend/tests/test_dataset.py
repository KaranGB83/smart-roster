"""The sample dataset reflects the brief's staffing pattern and generates cleanly."""
from collections import defaultdict

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.seed import seed


@pytest.fixture()
def seeded(client):
    with Session(get_engine()) as db:
        seed(db)
    return client


def test_staffing_pattern(seeded):
    rows = seeded.get("/assignment-details").json()
    by_brand, by_bp, by_emp = defaultdict(set), defaultdict(set), defaultdict(list)
    for r in rows:
        by_brand[r["brand"]].add(r["employee_id"])
        by_bp[r["brand_process_id"]].add(r["employee_id"])
        by_emp[r["employee_id"]].append(r)
    sizes = [len(s) for s in by_brand.values()]
    assert len(sizes) == 30 and sizes.count(1) == 24                       # 80% single resource
    assert all(2 <= n <= 3 for n in sizes if n > 1)                        # the rest have 2-3 people
    assert any(len(s) > 1 for s in by_bp.values())                         # a process with >1 person
    assert sum(1 for v in by_emp.values() if len({x["brand_id"] for x in v}) > 1) >= 3   # shared people
    assert sum(1 for v in by_emp.values() if len({x["process_id"] for x in v}) > 1) >= 10
    assert all(sum(x["allocation_pct"] for x in v) == 100 for v in by_emp.values())
    assert len(by_emp) == 36                                               # everyone is assigned


def test_calendars_and_rules_are_varied(seeded):
    bps = seeded.get("/brand-processes").json()
    assert {b["calendar"] for b in bps} == {"all_365", "daily_ex_holidays", "sun_holiday_off", "custom"}
    assert max(b["min_staff"] for b in seeded.get("/coverage-rules").json()) >= 2
    assert len(seeded.get("/holidays").json()) >= 4
    statuses = {lv["status"] for lv in seeded.get("/leaves").json()}
    assert statuses == {"approved", "pending", "rejected"}
    pods = seeded.get("/pods").json()
    leads = [e for e in seeded.get("/employees").json() if e["is_pod_lead"]]
    assert len(pods) == 6 and len(leads) == 6 and all(p["lead_id"] for p in pods)


@pytest.mark.parametrize("month", ["2026-12-01", "2027-01-01"])
def test_demo_months_generate_without_gaps(seeded, month):
    out = seeded.post("/rosters/generate", json={"month_start": month}).json()
    assert out["solver_status"] in ("optimal", "feasible")
    assert out["gap_count"] == 0 and out["publishable"] is True


def test_holiday_on_a_sunday_is_the_weekly_off_not_an_extra_one(seeded):
    # 8 Nov 2026 is a Sunday and a public holiday. Lines closed on Sundays must not need a second off day.
    out = seeded.post("/rosters/generate", json={"month_start": "2026-11-01"}).json()
    assert not [g for g in out["gaps"] if g["label"] in ("Kreo Wear · RET", "Orbit Gadgets · ACC")]
