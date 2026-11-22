"""ORM models. They mirror supabase/schema.sql, which remains the source of truth for DDL."""
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

CalendarType = PGEnum("all_365", "daily_ex_holidays", "sun_holiday_off", "custom",
                      name="calendar_type", create_type=False)
DayStatus = PGEnum("working", "weekly_off", "holiday_off", "leave", "comp_off",
                   name="day_status", create_type=False)
LeaveType = PGEnum("planned_leave", "sick_leave", "comp_off", name="leave_type", create_type=False)
ApprovalStatus = PGEnum("pending", "approved", "rejected", name="approval_status", create_type=False)
RosterStatus = PGEnum("draft", "published", "archived", name="roster_status", create_type=False)
Severity = PGEnum("error", "warning", "info", name="severity", create_type=False)

PK = dict(primary_key=True, server_default=text("gen_random_uuid()"))


class Pod(Base):
    __tablename__ = "pods"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    name: Mapped[str] = mapped_column(Text, unique=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    pod_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pods.id", ondelete="SET NULL"))
    is_pod_lead: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    weekly_offs_per_week: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    max_consecutive_days: Mapped[int] = mapped_column(SmallInteger, server_default=text("6"))
    preferred_off_days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    name: Mapped[str] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Process(Base):
    __tablename__ = "processes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandProcess(Base):
    __tablename__ = "brand_processes"
    __table_args__ = (UniqueConstraint("brand_id", "process_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id", ondelete="RESTRICT"))
    calendar: Mapped[str] = mapped_column(CalendarType, server_default=text("'daily_ex_holidays'"))
    operating_days: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{1,2,3,4,5,6,7}'"))
    min_staff: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class CoverageRule(Base):
    __tablename__ = "coverage_rules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    brand_process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brand_processes.id", ondelete="CASCADE"))
    day_of_week: Mapped[int | None] = mapped_column(SmallInteger)
    on_date: Mapped[date | None] = mapped_column(Date)
    min_staff: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str | None] = mapped_column(Text)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("employee_id", "brand_process_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    brand_process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brand_processes.id", ondelete="CASCADE"))
    allocation_pct: Mapped[int] = mapped_column(SmallInteger, server_default=text("100"))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class Holiday(Base):
    __tablename__ = "holidays"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    on_date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(Text)


class Leave(Base):
    __tablename__ = "leaves"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(LeaveType, server_default=text("'planned_leave'"))
    status: Mapped[str] = mapped_column(ApprovalStatus, server_default=text("'approved'"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    name: Mapped[str] = mapped_column(Text, unique=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class Roster(Base):
    __tablename__ = "rosters"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    month_start: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(Text, server_default=text("'Draft'"))
    status: Mapped[str] = mapped_column(RosterStatus, server_default=text("'draft'"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rosters.id", ondelete="SET NULL"))
    params: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RosterEntry(Base):
    __tablename__ = "roster_entries"
    __table_args__ = (UniqueConstraint("roster_id", "employee_id", "on_date"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    roster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rosters.id", ondelete="CASCADE"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    on_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(DayStatus)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    is_manual: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_locked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Conflict(Base):
    __tablename__ = "conflicts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    roster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rosters.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(Severity)
    code: Mapped[str] = mapped_column(Text)
    on_date: Mapped[date | None] = mapped_column(Date)
    brand_process_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brand_processes.id", ondelete="CASCADE"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    message: Mapped[str] = mapped_column(Text)
    suggestions: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    resolved: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
