"""DB <-> solver translation."""
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .calendar import month_days
from .domain import (AssignmentIn, BrandProcessIn, CoverageRuleIn, EmployeeIn, LeaveIn, Problem,
                     Result)


def load_problem(db: Session, month_start: date, base_roster_id: UUID | None = None) -> Problem:
    days = month_days(month_start)
    first, last = days[0], days[-1]

    employees = [
        EmployeeIn(str(e.id), e.full_name, e.weekly_offs_per_week, e.max_consecutive_days,
                   frozenset(e.preferred_off_days or []))
        for e in db.scalars(select(m.Employee).where(m.Employee.is_active))
    ]

    bp_rows = db.execute(
        select(m.BrandProcess, m.Brand, m.Process)
        .join(m.Brand, m.Brand.id == m.BrandProcess.brand_id)
        .join(m.Process, m.Process.id == m.BrandProcess.process_id)
        .where(m.BrandProcess.is_active, m.Brand.is_active)
    ).all()
    bps = [
        BrandProcessIn(str(bp.id), f"{b.name} · {p.code}", bp.calendar,
                       frozenset(bp.operating_days or []), bp.min_staff,
                       bp.effective_from, bp.effective_to)
        for bp, b, p in bp_rows
        if (bp.effective_to is None or bp.effective_to >= first)
        and (bp.effective_from is None or bp.effective_from <= last)
    ]
    bp_ids = {b.id for b in bps}

    assignments = [
        AssignmentIn(str(a.employee_id), str(a.brand_process_id), a.effective_from, a.effective_to)
        for a in db.scalars(select(m.Assignment))
        if str(a.brand_process_id) in bp_ids
    ]
    holidays = {h.on_date: h.name for h in db.scalars(
        select(m.Holiday).where(m.Holiday.on_date.between(first, last)))}
    leaves = [  # only APPROVED leave blocks a person; pending/rejected do not
        LeaveIn(str(lv.employee_id), lv.start_date, lv.end_date,
                "comp_off" if lv.type == "comp_off" else "leave")
        for lv in db.scalars(select(m.Leave).where(
            m.Leave.status == "approved", m.Leave.start_date <= last, m.Leave.end_date >= first))
    ]
    rules = [
        CoverageRuleIn(str(r.brand_process_id), r.min_staff, r.day_of_week, r.on_date)
        for r in db.scalars(select(m.CoverageRule)) if str(r.brand_process_id) in bp_ids
    ]
    locked: dict[tuple[str, date], str] = {}
    if base_roster_id:
        for en in db.scalars(select(m.RosterEntry).where(
                m.RosterEntry.roster_id == base_roster_id, m.RosterEntry.is_locked)):
            locked[(str(en.employee_id), en.on_date)] = en.status
    return Problem(month_start, employees, bps, assignments, holidays, leaves, rules, locked)


def save_result(db: Session, problem: Problem, result: Result, *, name: str,
                parent_id: UUID | None, params: dict) -> m.Roster:
    roster = m.Roster(month_start=problem.month_start, name=name, parent_id=parent_id, params=params)
    db.add(roster)
    db.flush()
    db.add_all([
        m.RosterEntry(roster_id=roster.id, employee_id=UUID(eid), on_date=d, status=status,
                      is_manual=(eid, d) in problem.locked, is_locked=(eid, d) in problem.locked)
        for (eid, d), status in result.entries.items()
    ])
    db.add_all([
        m.Conflict(roster_id=roster.id, severity="error", code=g.code, on_date=g.on_date,
                   brand_process_id=UUID(g.bp_id), message=g.message,
                   suggestions=[{"cause": g.cause, "staff": g.staff}])
        for g in result.gaps
    ])
    db.commit()
    db.refresh(roster)
    return roster
