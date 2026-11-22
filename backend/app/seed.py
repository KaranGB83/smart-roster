"""Sample data: 36 employees, 6 pods, 25 brands (20 single-resource = 80%, 5 multi-resource).
All names are fictional. Run:  python -m app.seed --reset
Holidays are sample data and editable in the app, not an authoritative Maharashtra list."""
import argparse
from datetime import date, time

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models as m

NAMES = [
    "Aarav Sharma", "Diya Patel", "Rohan Mehta", "Ananya Iyer", "Kabir Singh", "Meera Nair",
    "Vihaan Gupta", "Isha Reddy", "Arjun Kulkarni", "Sneha Joshi", "Rahul Verma", "Priya Desai",
    "Aditya Rao", "Neha Kapoor", "Siddharth Menon", "Pooja Shah", "Karthik Pillai", "Riya Malhotra",
    "Manish Yadav", "Tanvi Bhatt", "Yash Chauhan", "Kavya Bose", "Nikhil Jain", "Shruti Pawar",
    "Harsh Agarwal", "Divya Sethi", "Varun Khanna", "Aisha Khan", "Omkar Patil", "Simran Kaur",
    "Gaurav Mishra", "Lakshmi Naidu", "Rajat Saxena", "Tara Fernandes", "Zoya Qureshi", "Mohit Thakur",
]
PODS = ["Pod Alpha", "Pod Bravo", "Pod Charlie", "Pod Delta", "Pod Echo", "Pod Foxtrot"]
PROCESSES = [("CS", "Customer Support"), ("ACC", "Abandoned Cart Conversion"),
             ("RET", "Retention"), ("NDR", "Non-Delivery Report")]
SUN_OFF, DAILY, ALL365 = "sun_holiday_off", "daily_ex_holidays", "all_365"
MON_FRI, MON_SAT = [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6]

# (brand, [(process, calendar, operating_days or None, min_staff)])  -> ONE dedicated employee each
SINGLES = [
    ("Aurora Skincare", [("CS", SUN_OFF, None, 1)]),
    ("Bloom Naturals", [("CS", SUN_OFF, None, 1), ("ACC", SUN_OFF, None, 1)]),
    ("CedarCo Home", [("CS", SUN_OFF, None, 1), ("RET", "custom", MON_FRI, 1)]),
    ("Dazzle Jewels", [("CS", SUN_OFF, None, 1), ("NDR", SUN_OFF, None, 1)]),
    ("EcoNest", [("CS", SUN_OFF, None, 1)]),
    ("Fable Footwear", [("CS", SUN_OFF, None, 1), ("ACC", SUN_OFF, None, 1), ("RET", SUN_OFF, None, 1)]),
    ("GreenLeaf Tea", [("CS", SUN_OFF, None, 1), ("ACC", SUN_OFF, None, 1)]),
    ("Honeycomb Snacks", [("CS", SUN_OFF, None, 1)]),
    ("Indigo Threads", [("CS", "custom", MON_FRI, 1)]),
    ("Juno Kids", [("CS", "custom", MON_FRI, 1), ("ACC", "custom", MON_FRI, 1)]),
    ("Kiwi Pets", [("CS", "custom", MON_FRI, 1)]),
    ("Lumen Lighting", [("CS", "custom", MON_FRI, 1), ("NDR", "custom", MON_FRI, 1)]),
    ("Mocha Roasters", [("CS", "custom", MON_SAT, 1)]),
    ("Nimbus Gadgets", [("CS", "custom", MON_SAT, 1), ("RET", "custom", MON_SAT, 1)]),
    ("Orchid Fragrances", [("CS", "custom", MON_SAT, 1)]),
    ("Pebble Toys", [("CS", "custom", MON_SAT, 1), ("ACC", SUN_OFF, None, 1)]),
    ("Quill Stationery", [("CS", SUN_OFF, None, 1), ("NDR", SUN_OFF, None, 1)]),
    ("Ruby Activewear", [("CS", SUN_OFF, None, 1)]),
    ("Saffron Spices", [("CS", SUN_OFF, None, 1), ("RET", SUN_OFF, None, 1)]),
    ("Tulip Organics", [("CS", SUN_OFF, None, 1)]),
]
# Multi-resource brands: brand -> {process: (calendar, min, [employee numbers (1-based)])}
MULTI = {
    "Glowberry": {"CS": (ALL365, 1, [21, 22]), "ACC": (SUN_OFF, 1, [23]), "NDR": (DAILY, 1, [22, 23])},
    "Urban Nest": {"CS": (ALL365, 1, [24, 25, 26]), "NDR": (SUN_OFF, 1, [25, 26])},
    "Kreo Wear": {"CS": (DAILY, 1, [27, 28]), "ACC": (SUN_OFF, 1, [28])},
    "Veda Foods": {"CS": (ALL365, 1, [29, 30]), "RET": (SUN_OFF, 1, [31]), "NDR": (DAILY, 1, [30, 31])},
    "Pawsome": {"CS": (ALL365, 1, [32, 33]), "ACC": (SUN_OFF, 1, [33])},
}
# Floating backups (employees 34-36): (employee number, brand, process)
BACKUPS = [(34, "Glowberry", "CS"), (34, "Veda Foods", "CS"), (35, "Urban Nest", "CS"),
           (35, "Pawsome", "CS"), (36, "Kreo Wear", "CS"), (36, "Glowberry", "NDR")]

HOLIDAYS = [(date(2026, 12, 25), "Christmas Day"), (date(2026, 12, 31), "Year-end holiday (sample)"),
            (date(2027, 1, 26), "Republic Day")]


def seed(db: Session) -> dict:
    db.execute(text("truncate audit_log, conflicts, roster_entries, rosters, shifts, leaves, holidays, "
                    "assignments, coverage_rules, brand_processes, processes, brands, employees, pods "
                    "restart identity cascade"))
    pods = [m.Pod(name=n) for n in PODS]
    db.add_all(pods)
    db.flush()
    emps = []
    for i, name in enumerate(NAMES, start=1):
        pref = [7] if i % 5 == 0 else [3] if i % 7 == 0 else [6, 7] if i % 11 == 0 else []
        emps.append(m.Employee(
            code=f"EMP-{i:03d}", full_name=name, email=f"{name.split()[0].lower()}{i}@example.com",
            pod_id=pods[(i - 1) // 6].id, is_pod_lead=((i - 1) % 6 == 0), preferred_off_days=pref))
    db.add_all(emps)
    db.flush()
    for k, pod in enumerate(pods):
        pod.lead_id = emps[k * 6].id
    procs = {c: m.Process(code=c, name=n) for c, n in PROCESSES}
    db.add_all(procs.values())
    db.flush()

    bps: dict[tuple[str, str], m.BrandProcess] = {}

    def add_bp(brand, proc, cal, days, min_staff):
        bp = m.BrandProcess(brand_id=brand.id, process_id=procs[proc].id, calendar=cal,
                            operating_days=days or [1, 2, 3, 4, 5, 6, 7], min_staff=min_staff)
        db.add(bp)
        db.flush()
        bps[(brand.name, proc)] = bp
        return bp

    for idx, (bname, plist) in enumerate(SINGLES):
        brand = m.Brand(name=bname)
        db.add(brand)
        db.flush()
        for proc, cal, days, mn in plist:
            bp = add_bp(brand, proc, cal, days, mn)
            db.add(m.Assignment(employee_id=emps[idx].id, brand_process_id=bp.id))
    for bname, plist in MULTI.items():
        brand = m.Brand(name=bname, notes="Multi-resource brand")
        db.add(brand)
        db.flush()
        for proc, (cal, mn, members) in plist.items():
            bp = add_bp(brand, proc, cal, None, mn)
            for n in members:
                db.add(m.Assignment(employee_id=emps[n - 1].id, brand_process_id=bp.id))
    for n, bname, proc in BACKUPS:
        db.add(m.Assignment(employee_id=emps[n - 1].id, brand_process_id=bps[(bname, proc)].id,
                            allocation_pct=40, is_primary=False))

    db.add_all([m.Holiday(on_date=d, name=n) for d, n in HOLIDAYS])
    db.add(m.Shift(name="General", start_time=time(10, 0), end_time=time(19, 0)))
    # coverage rules: weekday and date-specific minimums
    db.add(m.CoverageRule(brand_process_id=bps[("Urban Nest", "CS")].id, day_of_week=6, min_staff=2,
                          reason="Saturday volume"))
    db.add(m.CoverageRule(brand_process_id=bps[("Glowberry", "CS")].id, on_date=date(2026, 12, 12),
                          min_staff=2, reason="12.12 sale day"))
    # leaves for the demo month (December 2026)
    e = lambda n: emps[n - 1].id  # noqa: E731
    db.add_all([
        m.Leave(employee_id=e(22), start_date=date(2026, 12, 14), end_date=date(2026, 12, 15),
                type="planned_leave", status="approved", reason="Family event"),
        m.Leave(employee_id=e(24), start_date=date(2026, 12, 20), end_date=date(2026, 12, 20),
                type="comp_off", status="approved", reason="Worked previous holiday"),
        m.Leave(employee_id=e(34), start_date=date(2026, 12, 28), end_date=date(2026, 12, 30),
                type="planned_leave", status="approved"),
        # PENDING leave for a single-resource brand: approving it is the demo "change" scenario
        m.Leave(employee_id=e(5), start_date=date(2026, 12, 9), end_date=date(2026, 12, 9),
                type="planned_leave", status="pending", reason="Personal work"),
    ])
    db.commit()
    return {"employees": len(emps), "pods": len(pods), "brands": len(SINGLES) + len(MULTI),
            "brand_processes": len(bps)}


if __name__ == "__main__":
    from .db import get_db

    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe all data and load the sample set")
    args = ap.parse_args()
    if not args.reset:
        raise SystemExit("This replaces ALL data. Re-run with --reset to confirm.")
    session = next(get_db())
    print(seed(session))
