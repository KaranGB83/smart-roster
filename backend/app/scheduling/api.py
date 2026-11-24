from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import RosterRead
from .loader import load_problem, save_result, sync_conflicts
from .validator import summarize, validate
from .solver import solve

router = APIRouter(prefix="/rosters", tags=["roster generation"])


class GenerateRequest(BaseModel):
    month_start: date
    name: str = "Generated draft"
    base_roster_id: UUID | None = Field(
        default=None, description="Keep this roster's locked cells fixed (regeneration).")
    time_limit_seconds: float = Field(default=20, gt=0, le=120)

    @model_validator(mode="after")
    def first_of_month(self):
        if self.month_start.day != 1:
            raise ValueError("month_start must be the first day of a month")
        return self


class GapOut(BaseModel):
    bp_id: str
    label: str
    on_date: date
    required: int
    covered: int
    code: str
    cause: str
    message: str
    staff: dict[str, str]


class GenerateResponse(BaseModel):
    roster: RosterRead | None
    solver_status: str
    solve_seconds: float
    coverage_slots: int
    gap_count: int
    warning_count: int = 0
    publishable: bool = False
    gaps: list[GapOut]
    warnings: list[str]


@router.post("/generate", response_model=GenerateResponse)
def generate_roster(body: GenerateRequest, db: Session = Depends(get_db)):
    """Generate a draft roster for the month. Coverage shortfalls are returned and stored as
    conflicts, never hidden."""
    problem = load_problem(db, body.month_start, body.base_roster_id)
    if not problem.employees:
        raise HTTPException(422, "no active employees to roster")
    result = solve(problem, time_limit=body.time_limit_seconds)
    roster, summary = None, {"warnings": 0, "publishable": False}
    if result.status in ("optimal", "feasible"):
        roster = save_result(db, problem, result, name=body.name, parent_id=body.base_roster_id,
                             params={"time_limit_seconds": body.time_limit_seconds,
                                     "solver_status": result.status})
        issues = validate(problem, result.entries)       # errors + warnings, stored for the manager
        sync_conflicts(db, roster.id, issues)
        summary = summarize(issues)
    return GenerateResponse(
        roster=roster, solver_status=result.status, solve_seconds=result.wall_time,
        coverage_slots=result.coverage_slots, gap_count=len(result.gaps),
        warning_count=summary["warnings"], publishable=summary["publishable"],
        gaps=[GapOut(**g.__dict__) for g in result.gaps], warnings=result.warnings)
