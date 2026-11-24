"""DB <-> solver translation."""
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import models as m
from .calendar import month_days
from .domain import (COVERAGE_CODES, AssignmentIn, BrandProcessIn, CoverageRuleIn, EmployeeIn, Issue,
                     LeaveIn, Problem, Result)


def load_problem(db: Session, month_start: date, base_roster_id: UUID | None = None) -> Problem:
    days = month_days(month_start)
    first, last = days[0], days[-1]

    employees = [
        EmployeeIn(str(e.id), e.full_name, e.weekly_offs_per_week, e.max_consecutive_days,
                   frozenset(e.preferred_off_days or []), str(e.pod_id) if e.pod_id else None)
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
    db.commit()
    db.refresh(roster)
    return roster


def load_roster_context(db: Session, roster: m.Roster) -> tuple[Problem, dict]:
    """Problem for the roster's month (its locked cells pinned) + its current cells."""
    problem = load_problem(db, roster.month_start, base_roster_id=roster.id)
    entries = {(str(en.employee_id), en.on_date): en.status for en in db.scalars(
        select(m.RosterEntry).where(m.RosterEntry.roster_id == roster.id))}
    return problem, entries


def _ckey(code, bp, emp, on_date):
    return ("COVERAGE" if code in COVERAGE_CODES else code, str(bp) if bp else None,
            str(emp) if emp else None, on_date)


def sync_conflicts(db: Session, roster_id: UUID, issues: list[Issue]) -> None:
    """Replace stored conflicts with the latest error/warning issues, keeping 'resolved' flags."""
    old = db.scalars(select(m.Conflict).where(m.Conflict.roster_id == roster_id)).all()
    resolved = {_ckey(c.code, c.brand_process_id, c.employee_id, c.on_date) for c in old if c.resolved}
    db.execute(delete(m.Conflict).where(m.Conflict.roster_id == roster_id))
    db.add_all([
        m.Conflict(roster_id=roster_id, severity=i.severity, code=i.code, on_date=i.on_date,
                   brand_process_id=UUID(i.bp_id) if i.bp_id else None,
                   employee_id=UUID(i.employee_id) if i.employee_id else None,
                   message=i.message, suggestions=[i.details] if i.details else [],
                   resolved=i.key in resolved)
        for i in issues if i.severity != "info"
    ])
    db.commit()


def upsert_cells(db: Session, roster_id: UUID, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = insert(m.RosterEntry).values([{**r, "roster_id": roster_id} for r in rows])
    stmt = stmt.on_conflict_do_update(
        index_elements=["roster_id", "employee_id", "on_date"],
        set_={c: stmt.excluded[c] for c in ("status", "shift_id", "is_manual", "is_locked")})
    db.execute(stmt)
