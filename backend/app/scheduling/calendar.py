"""Operating-calendar logic: when does a brand process need coverage? (not who works when)."""
import calendar as _cal
from datetime import date, timedelta

from .domain import AssignmentIn, BrandProcessIn, CoverageRuleIn

OPEN, CLOSED_HOLIDAY, CLOSED_REGULAR = "open", "closed_holiday", "closed_regular"


def month_days(month_start: date) -> list[date]:
    n = _cal.monthrange(month_start.year, month_start.month)[1]
    return [month_start + timedelta(days=i) for i in range(n)]


def in_effect(bp: BrandProcessIn, d: date) -> bool:
    return (bp.effective_from is None or d >= bp.effective_from) and (
        bp.effective_to is None or d <= bp.effective_to)


def assignment_active(a: AssignmentIn, d: date) -> bool:
    return (a.effective_from is None or d >= a.effective_from) and (
        a.effective_to is None or d <= a.effective_to)


def open_state(bp: BrandProcessIn, d: date, holidays) -> str:
    """OPEN, or why it is closed. A day closed ONLY because of a public holiday is CLOSED_HOLIDAY;
    a day closed by the weekly pattern (e.g. Sunday) is CLOSED_REGULAR even if it is also a holiday."""
    if not in_effect(bp, d):
        return CLOSED_REGULAR
    wd = d.isoweekday()
    if bp.calendar == "all_365":
        return OPEN
    if bp.calendar == "daily_ex_holidays":
        regular_open = True
    elif bp.calendar == "sun_holiday_off":
        regular_open = wd != 7
    else:  # custom: listed weekdays; public holidays are closed
        regular_open = wd in bp.operating_days
    if not regular_open:
        return CLOSED_REGULAR
    return CLOSED_HOLIDAY if d in holidays else OPEN


def required_staff(bp: BrandProcessIn, d: date, rules: list[CoverageRuleIn]) -> int:
    """date rule > weekday rule > process default."""
    for r in rules:
        if r.on_date == d:
            return r.min_staff
    for r in rules:
        if r.on_date is None and r.day_of_week == d.isoweekday():
            return r.min_staff
    return bp.min_staff
