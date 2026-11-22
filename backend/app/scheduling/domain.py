"""Plain dataclasses shared by the solver, loader and (Stage 4) validator. No DB or web imports."""
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class EmployeeIn:
    id: str
    name: str
    weekly_offs: int = 1
    max_consecutive: int = 6
    preferred_off: frozenset[int] = frozenset()  # ISO weekdays 1..7 (soft)


@dataclass(frozen=True)
class BrandProcessIn:
    id: str
    label: str                                # "Brand · CS"
    calendar: str                             # all_365 | daily_ex_holidays | sun_holiday_off | custom
    operating_days: frozenset[int] = frozenset(range(1, 8))  # used by 'custom'
    min_staff: int = 1
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class AssignmentIn:
    employee_id: str
    bp_id: str
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class LeaveIn:
    employee_id: str
    start: date
    end: date
    kind: str = "leave"                       # leave | comp_off


@dataclass(frozen=True)
class CoverageRuleIn:
    bp_id: str
    min_staff: int
    day_of_week: int | None = None            # ISO weekday
    on_date: date | None = None               # date rule beats weekday rule


@dataclass
class Problem:
    month_start: date
    employees: list[EmployeeIn]
    brand_processes: list[BrandProcessIn]
    assignments: list[AssignmentIn]
    holidays: dict[date, str] = field(default_factory=dict)
    leaves: list[LeaveIn] = field(default_factory=list)
    coverage_rules: list[CoverageRuleIn] = field(default_factory=list)
    # cells a human pinned: (employee_id, date) -> 'working' | 'weekly_off' | leave-like
    locked: dict[tuple[str, date], str] = field(default_factory=dict)


@dataclass
class Gap:
    bp_id: str
    label: str
    on_date: date
    required: int
    covered: int
    code: str                                 # NO_COVERAGE | UNDER_MIN_STAFF
    cause: str                                # unavailable_staff | weekly_off_limits
    message: str
    staff: dict[str, str]                     # assignee name -> status that day


@dataclass
class Result:
    status: str                               # optimal | feasible | infeasible | error
    entries: dict[tuple[str, date], str] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    objective: float | None = None
    wall_time: float = 0.0
    coverage_slots: int = 0
