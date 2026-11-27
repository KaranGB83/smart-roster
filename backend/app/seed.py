"""Sample data: 36 employees, 6 pods, 30 brands (24 single-resource = 80%, 6 multi-resource).
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
PODS = ["Beauty Pod", "Home Pod", "Fashion Pod", "Food Pod", "Pets & Kids Pod", "Gadgets Pod"]
PROCESSES = [("CS", "Customer Support"), ("ACC", "Abandoned Cart Conversion"),
             ("RET", "Retention"), ("NDR", "Non-Delivery Report")]
SUN_OFF, DAILY, ALL365 = "sun_holiday_off", "daily_ex_holidays", "all_365"
MON_FRI, MON_SAT = [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6]
S = lambda p, cal=SUN_OFF, days=None: (p, cal, days, 1)  # noqa: E731

# 24 single-resource brands. Brand i is handled end to end by employee i+1 (EMP-001..024),
# four per pod; the first of each four is the pod lead.
SINGLES = [
    ("Aurora Skincare", [S("CS"), S("ACC")]),
    ("Bloom Naturals", [S("CS"), S("ACC"), S("RET")]),
    ("Orchid Fragrances", [S("CS", "custom", MON_SAT)]),
    ("Tulip Organics", [S("CS")]),
    ("EcoNest", [S("CS")]),
    ("CedarCo Home", [S("CS"), S("RET", "custom", MON_FRI)]),
    ("Lumen Lighting", [S("CS", "custom", MON_FRI), S("NDR", "custom", MON_FRI)]),
    ("Umbra Candles", [S("CS")]),
    ("Fable Footwear", [S("CS"), S("ACC"), S("RET")]),
    ("Dazzle Jewels", [S("CS"), S("NDR")]),
    ("Indigo Threads", [S("CS", "custom", MON_FRI)]),
    ("Ruby Activewear", [S("CS"), S("ACC")]),
    ("GreenLeaf Tea", [S("CS"), S("ACC")]),
    ("Honeycomb Snacks", [S("CS")]),
    ("Mocha Roasters", [S("CS", "custom", MON_SAT)]),
    ("Saffron Spices", [S("CS"), S("RET")]),
    ("Kiwi Pets", [S("CS", "custom", MON_FRI)]),
    ("Juno Kids", [S("CS", "custom", MON_FRI), S("ACC", "custom", MON_FRI)]),
    ("Pebble Toys", [S("CS", "custom", MON_SAT), S("ACC")]),
    ("Willow Baby", [S("CS", "custom", MON_SAT)]),
    ("Nimbus Gadgets", [S("CS", "custom", MON_SAT), S("RET", "custom", MON_SAT)]),
    ("Quill Stationery", [S("CS"), S("NDR")]),
    ("Vista Optics", [S("CS")]),
    ("Yara Yoga", [S("CS"), S("RET")]),
]
# 6 multi-resource brands (20%): brand -> {process: (calendar, operating_days, [employee numbers])}
# Staff come from EMP-025..036 (two per pod). Some people cover several brands, some processes
# have two or three people, and 28, 30, 33, 34 work across brands.
MULTI = {
    "Glowberry": {"CS": (ALL365, None, [25, 26]), "ACC": (SUN_OFF, None, [28]), "NDR": (DAILY, None, [26, 28])},
    "Urban Nest": {"CS": (ALL365, None, [27, 28, 30]), "NDR": (SUN_OFF, None, [27])},
    "Kreo Wear": {"CS": (DAILY, None, [29, 30]), "RET": ("custom", MON_SAT, [29])},
    "Veda Foods": {"CS": (ALL365, None, [31, 32]), "RET": (SUN_OFF, None, [31, 34]), "NDR": (DAILY, None, [32, 34])},
    "Pawsome": {"CS": (ALL365, None, [33, 34]), "ACC": (SUN_OFF, None, [33])},
    "Orbit Gadgets": {"CS": (DAILY, None, [35, 36]), "ACC": (SUN_OFF, None, [35]),
                      "RET": ("custom", MON_FRI, [36]), "NDR": (SUN_OFF, None, [33])},
}

# Maharashtra public holidays for Nov 2026 - Jan 2027 (cleartax.in Maharashtra government list).
# Editable in the app; the operating calendar of each brand decides whether it is closed.
HOLIDAYS = [(date(2026, 11, 8), "Diwali (Lakshmi Pujan)"), (date(2026, 11, 9), "Diwali (Padwa)"),
            (date(2026, 11, 24), "Guru Nanak Jayanti"), (date(2026, 12, 25), "Christmas Day"),
            (date(2027, 1, 26), "Republic Day")]


def pod_index(n: int) -> int:
    """Employees 1-24 are single-brand owners (4 per pod), 25-36 multi-brand (2 per pod)."""
    return (n - 1) // 4 if n <= 24 else (n - 25) // 2


def seed(db: Session) -> dict:
    db.execute(text("truncate audit_log, conflicts, roster_entries, rosters, shifts, leaves, holidays, "
                    "assignments, coverage_rules, brand_processes, processes, brands, employees, pods "
                    "restart identity cascade"))
    pods = [m.Pod(name=n) for n in PODS]
    db.add_all(pods)
    db.flush()
    emps = []
    for i, name in enumerate(NAMES, start=1):
        # a few deliberate preferences; some will be honoured, a few cannot be
        pref = [7] if i % 5 == 0 else [3] if i % 7 == 0 else [6, 7] if i % 11 == 0 else []
        emps.append(m.Employee(
            code=f"EMP-{i:03d}", full_name=name, email=f"{name.split()[0].lower()}{i}@example.com",
            pod_id=pods[pod_index(i)].id, is_pod_lead=(i <= 24 and (i - 1) % 4 == 0),
            preferred_off_days=pref))
    db.add_all(emps)
    db.flush()
    for k, pod in enumerate(pods):
        pod.lead_id = emps[k * 4].id
    procs = {c: m.Process(code=c, name=n) for c, n in PROCESSES}
    db.add_all(procs.values())
    db.flush()

    bps: dict[tuple[str, str], m.BrandProcess] = {}
    pending: list[tuple[int, m.BrandProcess]] = []  # (employee number, brand-process)

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
            pending.append((idx + 1, add_bp(brand, proc, cal, days, mn)))
    for bname, plist in MULTI.items():
        brand = m.Brand(name=bname, notes="Multi-resource brand")
        db.add(brand)
        db.flush()
        for proc, (cal, days, members) in plist.items():
            bp = add_bp(brand, proc, cal, days, 1)
            pending.extend((n, bp) for n in members)

    # allocation: each person's 100% is split across the lines they are assigned to
    per_emp: dict[int, list[m.BrandProcess]] = {}
    for n, bp in pending:
        per_emp.setdefault(n, []).append(bp)
    for n, lines in per_emp.items():
        share, extra = divmod(100, len(lines))
        for k, bp in enumerate(lines):
            db.add(m.Assignment(employee_id=emps[n - 1].id, brand_process_id=bp.id,
                                allocation_pct=share + (extra if k == 0 else 0)))

    db.add_all([m.Holiday(on_date=d, name=n) for d, n in HOLIDAYS])
    db.add(m.Shift(name="General", start_time=time(10, 0), end_time=time(19, 0)))
    # coverage rules: weekday and date-specific minimums above the default
    rule = lambda b, p, n, reason, **kw: db.add(m.CoverageRule(  # noqa: E731
        brand_process_id=bps[(b, p)].id, min_staff=n, reason=reason, **kw))
    rule("Urban Nest", "CS", 2, "Saturday volume", day_of_week=6)
    rule("Glowberry", "CS", 2, "12.12 sale day", on_date=date(2026, 12, 12))
    rule("Orbit Gadgets", "CS", 2, "Flash sale", on_date=date(2026, 12, 11))
    rule("Veda Foods", "CS", 2, "Makar Sankranti sale", on_date=date(2027, 1, 14))

    e = lambda n: emps[n - 1].id  # noqa: E731
    L = lambda n, d1, d2, typ, status="approved", reason=None: m.Leave(  # noqa: E731
        employee_id=e(n), start_date=d1, end_date=d2, type=typ, status=status, reason=reason)
    db.add_all([
        # December 2026: leave of people whose lines are shared, so cover exists
        L(26, date(2026, 12, 14), date(2026, 12, 15), "planned_leave", reason="Family event"),
        L(25, date(2026, 12, 21), date(2026, 12, 21), "comp_off", reason="Worked previous holiday"),
        L(30, date(2026, 12, 28), date(2026, 12, 30), "planned_leave"),
        # January 2027
        L(31, date(2027, 1, 5), date(2027, 1, 6), "sick_leave"),
        L(32, date(2027, 1, 12), date(2027, 1, 12), "planned_leave"),
        # REJECTED leave is ignored by the solver
        L(12, date(2026, 12, 16), date(2026, 12, 16), "planned_leave", "rejected", "Declined: client launch"),
        # PENDING leave of a single-resource brand owner: approving it is the demo "change" scenario
        L(5, date(2026, 12, 9), date(2026, 12, 9), "planned_leave", "pending", "Personal work"),
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
