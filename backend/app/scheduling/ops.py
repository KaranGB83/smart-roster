"""Operations on an existing roster: validate, suggest fixes, apply edits, handle leave changes."""
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..schemas import EntryUpsert
from .calendar import OPEN
from .changes import diff_issues, impact_of_leave
from .domain import Issue, Suggestion
from .index import Index
from .loader import load_roster_context, sync_conflicts, upsert_cells
from .suggest import suggest_for_gap
from .validator import summarize, validate

router = APIRouter(prefix="/rosters", tags=["roster operations"])


class IssueOut(BaseModel):
    code: str
    severity: str
    message: str
    on_date: date | None = None
    brand_process_id: str | None = None
    employee_id: str | None = None
    label: str | None = None
    details: dict[str, Any] = {}


class SuggestionOut(BaseModel):
    kind: str
    title: str
    detail: str
    edits: dict | None
    errors_before: int
    errors_after: int
    side_effects: list[str]


class Summary(BaseModel):
    errors: int
    warnings: int
    info: int
    publishable: bool


class ValidationOut(BaseModel):
    summary: Summary
    issues: list[IssueOut]


def issue_out(i: Issue) -> IssueOut:
    return IssueOut(code=i.code, severity=i.severity, message=i.message, on_date=i.on_date,
                    brand_process_id=i.bp_id, employee_id=i.employee_id, label=i.label, details=i.details)


def sug_out(s: Suggestion) -> SuggestionOut:
    return SuggestionOut(**{k: v for k, v in s.__dict__.items() if k != "rank"})


def get_roster(db: Session, roster_id: UUID, *, editable: bool = False) -> m.Roster:
    roster = db.get(m.Roster, roster_id)
    if roster is None:
        raise HTTPException(404, "roster not found")
    if editable and roster.status == "archived":
        raise HTTPException(409, "archived rosters cannot be changed")
    return roster


@router.post("/{roster_id}/validate", response_model=ValidationOut)
def validate_roster(roster_id: UUID, db: Session = Depends(get_db)):
    """Re-check the whole roster against every rule and refresh its stored conflicts."""
    roster = get_roster(db, roster_id)
    problem, entries = load_roster_context(db, roster)
    issues = validate(problem, entries)
    sync_conflicts(db, roster.id, issues)
    return ValidationOut(summary=Summary(**summarize(issues)), issues=[issue_out(i) for i in issues])


# ---------------------------------------------------------------- suggestions
class SuggestRequest(BaseModel):
    conflict_id: UUID | None = None
    brand_process_id: UUID | None = None
    on_date: date | None = None
    limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def need_target(self):
        if not self.conflict_id and not (self.brand_process_id and self.on_date):
            raise ValueError("give conflict_id, or brand_process_id and on_date")
        return self


@router.post("/{roster_id}/suggestions", response_model=list[SuggestionOut])
def suggest_fixes(roster_id: UUID, body: SuggestRequest, db: Session = Depends(get_db)):
    """Ranked, simulated fixes for a coverage gap. Post a suggestion's `edits` to /edits to apply it."""
    roster = get_roster(db, roster_id)
    bp_id, on_date = body.brand_process_id, body.on_date
    if body.conflict_id:
        c = db.get(m.Conflict, body.conflict_id)
        if c is None or c.roster_id != roster.id or not c.brand_process_id or not c.on_date:
            raise HTTPException(404, "conflict not found for this roster or not a coverage gap")
        bp_id, on_date = c.brand_process_id, c.on_date
    problem, entries = load_roster_context(db, roster)
    return [sug_out(s) for s in suggest_for_gap(problem, entries, str(bp_id), on_date, body.limit)]


# ---------------------------------------------------------------- edits
class AssignmentEdit(BaseModel):
    employee_id: UUID
    brand_process_id: UUID
    effective_from: date | None = None
    effective_to: date | None = None


class EditsRequest(BaseModel):
    entries: list[EntryUpsert] = []
    assignments: list[AssignmentEdit] = []


class ImpactOut(BaseModel):
    summary: Summary
    introduced: list[IssueOut]
    resolved: list[IssueOut]


def _apply_assignment(db: Session, a: AssignmentEdit) -> None:
    row = db.scalar(select(m.Assignment).where(m.Assignment.employee_id == a.employee_id,
                                               m.Assignment.brand_process_id == a.brand_process_id))
    if row is None:
        db.add(m.Assignment(employee_id=a.employee_id, brand_process_id=a.brand_process_id,
                            is_primary=False, allocation_pct=50,
                            effective_from=a.effective_from, effective_to=a.effective_to))
    elif row.effective_from and row.effective_to and a.effective_from and a.effective_to:
        row.effective_from = min(row.effective_from, a.effective_from)  # widen a temporary window
        row.effective_to = max(row.effective_to, a.effective_to)


@router.post("/{roster_id}/edits", response_model=ImpactOut)
def apply_edits(roster_id: UUID, body: EditsRequest, db: Session = Depends(get_db)):
    """Manual edit (or an applied suggestion): changes are saved, then validated, and the response
    says exactly which problems the edit introduced and which it fixed."""
    roster = get_roster(db, roster_id, editable=True)
    problem, entries = load_roster_context(db, roster)
    before = validate(problem, entries)
    for a in body.assignments:
        _apply_assignment(db, a)
    upsert_cells(db, roster.id, [{**e.model_dump(), "is_manual": True} for e in body.entries])
    db.commit()
    problem, entries = load_roster_context(db, roster)
    after = validate(problem, entries)
    sync_conflicts(db, roster.id, after)
    introduced, resolved = diff_issues(before, after)
    return ImpactOut(summary=Summary(**summarize(after)),
                     introduced=[issue_out(i) for i in introduced],
                     resolved=[issue_out(i) for i in resolved])


# ---------------------------------------------------------------- leave change
class LeaveChange(BaseModel):
    employee_id: UUID
    start_date: date
    end_date: date
    type: Literal["planned_leave", "sick_leave", "comp_off"] = "planned_leave"
    reason: str | None = None
    dry_run: bool = Field(default=True, description="true: only report the impact; false: apply it")

    @model_validator(mode="after")
    def ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class GapReport(BaseModel):
    issue: IssueOut
    suggestions: list[SuggestionOut]


class CoverageCheck(BaseModel):
    label: str
    on_date: date
    required: int
    working: int
    ok: bool


class LeaveImpact(BaseModel):
    applied: bool
    fully_absorbed: bool
    affected_brands: list[str]
    coverage_checks: list[CoverageCheck]
    new_gaps: list[GapReport]
    other_errors: list[IssueOut]
    summary: Summary


@router.post("/{roster_id}/leave-change", response_model=LeaveImpact)
def leave_change(roster_id: UUID, body: LeaveChange, db: Session = Depends(get_db)):
    """An employee becomes unavailable after the roster exists. Reports whether the rest of the team
    absorbs it, flags every new gap (across all the brands the person covers) with ranked fixes, and,
    unless dry_run, records the approved leave and updates the roster."""
    roster = get_roster(db, roster_id, editable=True)
    if db.get(m.Employee, body.employee_id) is None:
        raise HTTPException(404, "employee not found")
    problem, entries = load_roster_context(db, roster)
    kind = "comp_off" if body.type == "comp_off" else "leave"
    r = impact_of_leave(problem, entries, str(body.employee_id), body.start_date, body.end_date, kind)

    if not body.dry_run:
        db.add(m.Leave(employee_id=body.employee_id, start_date=body.start_date, end_date=body.end_date,
                       type=body.type, status="approved", reason=body.reason))
        cells = [{"employee_id": body.employee_id, "on_date": d, "status": kind, "shift_id": None,
                  "is_manual": True, "is_locked": False}
                 for (eid, d), st in r["entries"].items()
                 if eid == str(body.employee_id) and body.start_date <= d <= body.end_date]
        upsert_cells(db, roster.id, cells)
        db.commit()
        sync_conflicts(db, roster.id, r["issues_after"])

    return LeaveImpact(
        applied=not body.dry_run, fully_absorbed=r["fully_absorbed"], affected_brands=r["affected_brands"],
        coverage_checks=[CoverageCheck(**c) for c in r["checks"]],
        new_gaps=[GapReport(issue=issue_out(g["issue"]), suggestions=[sug_out(s) for s in g["suggestions"]])
                  for g in r["new_gaps"]],
        other_errors=[issue_out(i) for i in r["new_other_errors"]],
        summary=Summary(**summarize(r["issues_after"])))


# ---------------------------------------------------------------- coverage matrix
class CoverageCell(BaseModel):
    on_date: date
    state: Literal["open", "closed_holiday", "closed_regular"]
    required: int
    covered: int


class CoverageRow(BaseModel):
    brand_process_id: str
    brand: str
    process: str
    label: str
    employee_ids: list[str]
    cells: list[CoverageCell]


@router.get("/{roster_id}/coverage", response_model=list[CoverageRow])
def coverage_matrix(roster_id: UUID, db: Session = Depends(get_db)):
    """Per brand-process, per day: is it open, how many are needed, how many are rostered.
    Uses the same calendar/coverage logic as the validator, so the dashboard never re-implements rules."""
    roster = get_roster(db, roster_id)
    problem, entries = load_roster_context(db, roster)
    idx = Index(problem)
    rows = []
    for bp in sorted(problem.brand_processes, key=lambda b: b.label):
        brand, _, process = bp.label.partition(" · ")
        cells = []
        for d in idx.days:
            state = idx.state(bp.id, d)
            required = idx.required(bp.id, d) if state == OPEN else 0
            covered = sum(1 for mem in idx.members(bp.id, d) if entries.get((mem, d)) == "working")
            cells.append(CoverageCell(on_date=d, state=state, required=required, covered=covered))
        rows.append(CoverageRow(
            brand_process_id=bp.id, brand=brand, process=process, label=bp.label,
            employee_ids=sorted({a.employee_id for a in idx.asg_by_bp[bp.id]}), cells=cells))
    return rows
