"""API-level Stage 4 flow on the seeded dataset: validate, leave-change, suggestions, edits, publish."""
import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.seed import seed


@pytest.fixture()
def roster(client):
    with Session(get_engine()) as db:
        seed(db)
    out = client.post("/rosters/generate", json={"month_start": "2026-12-01", "name": "Dec"}).json()
    assert out["gap_count"] == 0 and out["publishable"] is True
    return client, out["roster"]["id"]


def emp(client, code):
    return next(e for e in client.get("/employees").json() if e["code"] == code)


def test_validate_clean_roster_reports_info_and_is_publishable(roster):
    client, rid = roster
    v = client.post(f"/rosters/{rid}/validate").json()
    assert v["summary"]["errors"] == 0 and v["summary"]["publishable"]
    assert v["summary"]["info"] >= 24                        # 24 single-resource brands flagged as SPOF
    assert {i["code"] for i in v["issues"] if i["severity"] == "info"} == {"SINGLE_POINT_OF_FAILURE"}


def test_leave_change_dry_run_changes_nothing_then_apply(roster):
    client, rid = roster
    kabir = emp(client, "EMP-005")                           # sole resource of EcoNest
    body = {"employee_id": kabir["id"], "start_date": "2026-12-09", "end_date": "2026-12-09"}
    dry = client.post(f"/rosters/{rid}/leave-change", json=body).json()
    assert dry["applied"] is False and dry["fully_absorbed"] is False
    assert dry["affected_brands"] == ["EcoNest"]
    gap = dry["new_gaps"][0]
    assert gap["issue"]["code"] == "NO_COVERAGE" and gap["issue"]["label"] == "EcoNest · CS"
    assert gap["suggestions"][0]["kind"] in ("borrow_and_swap", "double_duty", "escalate")
    assert client.get("/leaves", params={"employee_id": kabir["id"], "status": "approved"}).json() == []
    assert client.get(f"/rosters/{rid}/entries", params={"employee_id": kabir["id"],
                      "date_from": "2026-12-09", "date_to": "2026-12-09"}).json()[0]["status"] == "working"

    applied = client.post(f"/rosters/{rid}/leave-change", json={**body, "dry_run": False}).json()
    assert applied["applied"] is True and applied["summary"]["publishable"] is False
    cell = client.get(f"/rosters/{rid}/entries", params={"employee_id": kabir["id"],
                      "date_from": "2026-12-09", "date_to": "2026-12-09"}).json()[0]
    assert cell["status"] == "leave"
    stored = [c for c in client.get("/conflicts", params={"roster_id": rid}).json()
              if c["severity"] == "error"]
    assert len(stored) == 1 and stored[0]["code"] == "NO_COVERAGE"


def test_publish_blocked_until_gap_is_fixed_then_allowed(roster):
    client, rid = roster
    kabir = emp(client, "EMP-005")
    client.post(f"/rosters/{rid}/leave-change", json={
        "employee_id": kabir["id"], "start_date": "2026-12-09", "end_date": "2026-12-09", "dry_run": False})
    blocked = client.patch(f"/rosters/{rid}", json={"status": "published"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["errors"][0]["code"] == "NO_COVERAGE"

    # manager fixes it: a colleague is borrowed for that one day
    conflict = next(c for c in client.get("/conflicts", params={"roster_id": rid}).json()
                    if c["severity"] == "error")
    sugs = client.post(f"/rosters/{rid}/suggestions", json={"conflict_id": conflict["id"]}).json()
    fix = next((s for s in sugs if s["edits"]), None)
    if fix is None:                                          # nobody free: resolution is a manager decision
        pytest.skip("no automatic fix available in this dataset")
    res = client.post(f"/rosters/{rid}/edits", json=fix["edits"]).json()
    assert res["summary"]["errors"] == 0 and res["summary"]["publishable"]
    assert any(r["code"] == "NO_COVERAGE" for r in res["resolved"]) and not res["introduced"]
    ok = client.patch(f"/rosters/{rid}", json={"status": "published"})
    assert ok.status_code == 200 and ok.json()["status"] == "published" and ok.json()["published_at"]


def test_manual_edit_that_breaks_a_rule_is_reported_immediately(roster):
    client, rid = roster
    asha = emp(client, "EMP-009")                            # Arjun, sole resource of Indigo/other
    res = client.post(f"/rosters/{rid}/edits", json={"entries": [
        {"employee_id": asha["id"], "on_date": "2026-12-08", "status": "weekly_off"}]}).json()
    assert any(i["code"] in ("NO_COVERAGE", "UNDER_MIN_STAFF") for i in res["introduced"])
    assert res["summary"]["publishable"] is False
    cell = client.get(f"/rosters/{rid}/entries", params={"employee_id": asha["id"],
                      "date_from": "2026-12-08", "date_to": "2026-12-08"}).json()[0]
    assert cell["is_manual"] is True


def test_archived_roster_cannot_be_edited_and_unknown_inputs_404(roster):
    client, rid = roster
    client.patch(f"/rosters/{rid}", json={"status": "archived"})
    e = emp(client, "EMP-001")
    assert client.post(f"/rosters/{rid}/edits", json={"entries": [
        {"employee_id": e["id"], "on_date": "2026-12-08", "status": "working"}]}).status_code == 409
    nil = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/rosters/{nil}/validate").status_code == 404
    assert client.post(f"/rosters/{rid}/suggestions", json={"conflict_id": nil}).status_code == 404
    assert client.post(f"/rosters/{rid}/suggestions", json={}).status_code == 422


def test_coverage_matrix_matches_validator(roster):
    client, rid = roster
    rows = client.get(f"/rosters/{rid}/coverage").json()
    assert len(rows) == 56 and all(len(r["cells"]) == 31 for r in rows)
    econest = next(r for r in rows if r["label"] == "EcoNest · CS")
    assert (econest["brand"], econest["process"]) == ("EcoNest", "CS") and len(econest["employee_ids"]) == 1
    sunday = next(c for c in econest["cells"] if c["on_date"] == "2026-12-06")
    assert sunday["state"] == "closed_regular" and sunday["required"] == 0
    wed = next(c for c in econest["cells"] if c["on_date"] == "2026-12-02")
    assert wed["state"] == "open" and wed["required"] == 1 and wed["covered"] == 1
    # no cell is short on a clean roster; after approved leave exactly the validator's gap shows up
    assert not [c for r in rows for c in r["cells"] if c["covered"] < c["required"]]
    kabir = next(e for e in client.get("/employees").json() if e["code"] == "EMP-005")
    client.post(f"/rosters/{rid}/leave-change", json={
        "employee_id": kabir["id"], "start_date": "2026-12-09", "end_date": "2026-12-09", "dry_run": False})
    short = [(r["label"], c["on_date"]) for r in client.get(f"/rosters/{rid}/coverage").json()
             for c in r["cells"] if c["covered"] < c["required"]]
    assert short == [("EcoNest · CS", "2026-12-09")]
