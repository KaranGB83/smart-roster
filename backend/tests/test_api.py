def post(client, url, body, status=201):
    r = client.post(url, json=body)
    assert r.status_code == status, r.text
    return r.json()


def make_world(client):
    """pod + 2 employees + brand + CS process + brand_process + assignment."""
    pod = post(client, "/pods", {"name": "Pod A"})
    lead = post(client, "/employees", {"full_name": "Lead One", "pod_id": pod["id"], "is_pod_lead": True})
    emp = post(client, "/employees", {"full_name": "Asha", "pod_id": pod["id"], "email": "asha@example.com"})
    client.patch(f"/pods/{pod['id']}", json={"lead_id": lead["id"]})
    brand = post(client, "/brands", {"name": "Brand X"})
    proc = post(client, "/processes", {"code": "CS", "name": "Customer Support"})
    bp = post(client, "/brand-processes", {
        "brand_id": brand["id"], "process_id": proc["id"], "calendar": "all_365", "min_staff": 2})
    asg = post(client, "/assignments", {"employee_id": emp["id"], "brand_process_id": bp["id"]})
    return dict(pod=pod, lead=lead, emp=emp, brand=brand, proc=proc, bp=bp, asg=asg)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_crud_lifecycle_and_defaults(client):
    w = make_world(client)
    assert w["emp"]["weekly_offs_per_week"] == 1 and w["emp"]["max_consecutive_days"] == 6
    assert w["bp"]["operating_days"] == [1, 2, 3, 4, 5, 6, 7]
    # read, patch, list filter, delete
    assert client.get(f"/employees/{w['emp']['id']}").json()["full_name"] == "Asha"
    r = client.patch(f"/employees/{w['emp']['id']}", json={"preferred_off_days": [7]})
    assert r.json()["preferred_off_days"] == [7] and r.json()["full_name"] == "Asha"
    assert len(client.get("/employees").json()) == 2
    assert len(client.get("/employees", params={"pod_id": w["pod"]["id"]}).json()) == 2
    assert len(client.get("/assignments", params={"employee_id": w["emp"]["id"]}).json()) == 1
    assert client.delete(f"/assignments/{w['asg']['id']}").status_code == 204
    assert client.get(f"/assignments/{w['asg']['id']}").status_code == 404


def test_patch_keeps_validation(client):
    w = make_world(client)
    assert client.patch(f"/employees/{w['emp']['id']}", json={"weekly_offs_per_week": 9}).status_code == 422
    assert client.patch(f"/brand-processes/{w['bp']['id']}", json={"min_staff": -1}).status_code == 422


def test_constraint_errors_map_to_http(client):
    w = make_world(client)
    assert client.post("/brands", json={"name": "Brand X"}).status_code == 409          # unique
    assert client.post("/assignments", json={
        "employee_id": w["emp"]["id"], "brand_process_id": w["bp"]["id"]}).status_code == 409  # unique pair
    bad = "00000000-0000-0000-0000-000000000000"
    assert client.post("/assignments", json={
        "employee_id": bad, "brand_process_id": w["bp"]["id"]}).status_code == 409          # FK
    assert client.post("/employees", json={"full_name": "X", "preferred_off_days": [8]}).status_code == 422


def test_coverage_rule_needs_exactly_one_selector(client):
    w = make_world(client)
    base = {"brand_process_id": w["bp"]["id"], "min_staff": 3}
    post(client, "/coverage-rules", {**base, "day_of_week": 6})
    post(client, "/coverage-rules", {**base, "on_date": "2026-12-25", "reason": "Sale"})
    assert client.post("/coverage-rules", json=base).status_code == 422
    assert client.post("/coverage-rules", json={**base, "day_of_week": 6, "on_date": "2026-12-25"}).status_code == 422


def test_leave_and_holiday_validation(client):
    w = make_world(client)
    post(client, "/leaves", {"employee_id": w["emp"]["id"], "start_date": "2026-12-01", "end_date": "2026-12-03"})
    assert client.post("/leaves", json={
        "employee_id": w["emp"]["id"], "start_date": "2026-12-05", "end_date": "2026-12-01"}).status_code == 422
    post(client, "/holidays", {"on_date": "2026-12-25", "name": "Christmas"})
    assert client.post("/holidays", json={"on_date": "2026-12-25", "name": "Dup"}).status_code == 409


def test_assignment_details_view(client):
    w = make_world(client)
    rows = client.get("/assignment-details").json()
    assert len(rows) == 1
    assert rows[0]["brand"] == "Brand X" and rows[0]["process"] == "CS" and rows[0]["pod"] == "Pod A"


def test_roster_and_manual_entries(client):
    w = make_world(client)
    assert client.post("/rosters", json={"month_start": "2026-12-15"}).status_code == 422
    roster = post(client, "/rosters", {"month_start": "2026-12-01", "name": "Dec plan A"})
    assert roster["status"] == "draft"
    cells = [
        {"employee_id": w["emp"]["id"], "on_date": "2026-12-01", "status": "working"},
        {"employee_id": w["emp"]["id"], "on_date": "2026-12-02", "status": "weekly_off", "is_locked": True},
    ]
    r = client.put(f"/rosters/{roster['id']}/entries", json=cells)
    assert r.status_code == 200 and all(e["is_manual"] for e in r.json())
    # upsert same cell changes it, no duplicate
    client.put(f"/rosters/{roster['id']}/entries", json=[{**cells[0], "status": "leave"}])
    entries = client.get(f"/rosters/{roster['id']}/entries").json()
    assert len(entries) == 2 and entries[0]["status"] == "leave"
    assert len(client.get(f"/rosters/{roster['id']}/entries", params={"date_from": "2026-12-02"}).json()) == 1
    # an incomplete roster (2 cells for 2 employees) must not be publishable
    blocked = client.patch(f"/rosters/{roster['id']}", json={"status": "published"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["errors"]
    assert client.delete(f"/rosters/{roster['id']}").status_code == 204
