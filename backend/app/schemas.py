"""Pydantic request/response models. `*Update` models are generated from `*Create` (all optional)."""
from datetime import date, datetime, time
from typing import Annotated, Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, create_model, model_validator
from pydantic.fields import FieldInfo

Weekday = Annotated[int, Field(ge=1, le=7)]  # ISO: 1=Mon .. 7=Sun
CalendarKind = Literal["all_365", "daily_ex_holidays", "sun_holiday_off", "custom"]
DayStatusT = Literal["working", "weekly_off", "holiday_off", "leave", "comp_off"]
LeaveKind = Literal["planned_leave", "sick_leave", "comp_off"]
ApprovalT = Literal["pending", "approved", "rejected"]
RosterStatusT = Literal["draft", "published", "archived"]


def optional(model: type[BaseModel], name: str) -> type[BaseModel]:
    """Build a PATCH model: same fields and constraints, all optional, no defaults applied."""
    fields: dict[str, Any] = {}
    for fname, f in model.model_fields.items():
        fields[fname] = (Optional[f.annotation], FieldInfo.merge_field_infos(f, default=None))
    return create_model(name, **fields)


class ReadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ---- pods / employees
class PodCreate(BaseModel):
    name: str = Field(min_length=1)
    lead_id: UUID | None = None


class PodRead(PodCreate, ReadBase):
    created_at: datetime


class EmployeeCreate(BaseModel):
    code: str | None = None
    full_name: str = Field(min_length=1)
    email: EmailStr | None = None
    pod_id: UUID | None = None
    is_pod_lead: bool = False
    is_active: bool = True
    weekly_offs_per_week: int = Field(default=1, ge=0, le=3)
    max_consecutive_days: int = Field(default=6, ge=1, le=14)
    preferred_off_days: list[Weekday] = []


class EmployeeRead(EmployeeCreate, ReadBase):
    created_at: datetime


# ---- brands / processes
class BrandCreate(BaseModel):
    name: str = Field(min_length=1)
    is_active: bool = True
    notes: str | None = None


class BrandRead(BrandCreate, ReadBase):
    created_at: datetime


class ProcessCreate(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ProcessRead(ProcessCreate, ReadBase):
    created_at: datetime


class BrandProcessCreate(BaseModel):
    brand_id: UUID
    process_id: UUID
    calendar: CalendarKind = "daily_ex_holidays"
    operating_days: list[Weekday] = [1, 2, 3, 4, 5, 6, 7]
    min_staff: int = Field(default=1, ge=0)
    is_active: bool = True
    effective_from: date | None = None
    effective_to: date | None = None


class BrandProcessRead(BrandProcessCreate, ReadBase):
    pass


class CoverageRuleCreate(BaseModel):
    brand_process_id: UUID
    day_of_week: Weekday | None = None
    on_date: date | None = None
    min_staff: int = Field(ge=0)
    reason: str | None = None

    @model_validator(mode="after")
    def exactly_one_selector(self):
        if (self.day_of_week is None) == (self.on_date is None):
            raise ValueError("set exactly one of day_of_week or on_date")
        return self


class CoverageRuleRead(CoverageRuleCreate, ReadBase):
    pass


class AssignmentCreate(BaseModel):
    employee_id: UUID
    brand_process_id: UUID
    allocation_pct: int = Field(default=100, ge=1, le=100)
    is_primary: bool = True
    effective_from: date | None = None
    effective_to: date | None = None


class AssignmentRead(AssignmentCreate, ReadBase):
    pass


# ---- calendar / availability
class HolidayCreate(BaseModel):
    on_date: date
    name: str = Field(min_length=1)


class HolidayRead(HolidayCreate, ReadBase):
    pass


class LeaveCreate(BaseModel):
    employee_id: UUID
    start_date: date
    end_date: date
    type: LeaveKind = "planned_leave"
    status: ApprovalT = "approved"
    reason: str | None = None

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LeaveRead(LeaveCreate, ReadBase):
    created_at: datetime


class ShiftCreate(BaseModel):
    name: str = Field(min_length=1)
    start_time: time
    end_time: time


class ShiftRead(ShiftCreate, ReadBase):
    pass


# ---- rosters
class RosterCreate(BaseModel):
    month_start: date
    name: str = "Draft"
    parent_id: UUID | None = None
    params: dict = {}

    @model_validator(mode="after")
    def first_of_month(self):
        if self.month_start.day != 1:
            raise ValueError("month_start must be the first day of a month")
        return self


class RosterUpdate(BaseModel):
    name: str | None = None
    status: RosterStatusT | None = None
    params: dict | None = None


class RosterRead(ReadBase):
    month_start: date
    name: str
    status: RosterStatusT
    parent_id: UUID | None
    params: dict
    created_at: datetime
    published_at: datetime | None


class EntryUpsert(BaseModel):
    employee_id: UUID
    on_date: date
    status: DayStatusT
    shift_id: UUID | None = None
    is_locked: bool = False


class EntryRead(ReadBase):
    roster_id: UUID
    employee_id: UUID
    on_date: date
    status: DayStatusT
    shift_id: UUID | None
    is_manual: bool
    is_locked: bool


class ConflictRead(ReadBase):
    roster_id: UUID
    severity: Literal["error", "warning", "info"]
    code: str
    on_date: date | None
    brand_process_id: UUID | None
    employee_id: UUID | None
    message: str
    suggestions: list
    resolved: bool
    created_at: datetime
