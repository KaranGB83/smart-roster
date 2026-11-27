"""Pre-computed lookups shared by the solver, validator and suggestion engine."""
from collections import defaultdict
from datetime import date

from .calendar import CLOSED_HOLIDAY, CLOSED_REGULAR, OPEN, assignment_active, month_days, open_state, required_staff
from .domain import AssignmentIn, Problem


class Index:
    def __init__(self, p: Problem, extra: list[AssignmentIn] | tuple = ()):
        self.p = p
        self.days = month_days(p.month_start)
        self.emps = {e.id: e for e in p.employees}
        self.bps = {b.id: b for b in p.brand_processes}
        self.asg_by_emp = defaultdict(list)
        self.asg_by_bp = defaultdict(list)
        for a in [*p.assignments, *extra]:
            if a.employee_id in self.emps and a.bp_id in self.bps:
                self.asg_by_emp[a.employee_id].append(a)
                self.asg_by_bp[a.bp_id].append(a)
        self.rules = defaultdict(list)
        for r in p.coverage_rules:
            self.rules[r.bp_id].append(r)
        self.leave: dict[tuple[str, date], str] = {}
        for lv in p.leaves:
            if lv.employee_id in self.emps:
                for d in self.days:
                    if lv.start <= d <= lv.end:
                        self.leave[(lv.employee_id, d)] = "comp_off" if lv.kind == "comp_off" else "leave"
        self.has_any = {eid: any(assignment_active(a, d) for a in self.asg_by_emp[eid] for d in self.days)
                        for eid in self.emps}
        self._forced: dict[tuple[str, date], str | None] = {}

    def members(self, bp_id: str, d: date) -> list[str]:
        return [a.employee_id for a in self.asg_by_bp[bp_id] if assignment_active(a, d)]

    def required(self, bp_id: str, d: date) -> int:
        return required_staff(self.bps[bp_id], d, self.rules[bp_id])

    def state(self, bp_id: str, d: date) -> str:
        return open_state(self.bps[bp_id], d, self.p.holidays)

    def forced_off(self, eid: str, d: date) -> str | None:
        """'weekly_off' / 'holiday_off' when none of the person's processes is open that day."""
        k = (eid, d)
        if k not in self._forced:
            val = None
            if self.has_any[eid]:
                states = [self.state(a.bp_id, d) for a in self.asg_by_emp[eid] if assignment_active(a, d)]
                if OPEN not in states:
                    # a holiday on a day the person is off anyway (e.g. a Sunday for a line that
                    # is closed Sundays) is their weekly off, not an extra day off
                    val = "holiday_off" if CLOSED_HOLIDAY in states and CLOSED_REGULAR not in states else "weekly_off"
            self._forced[k] = val
        return self._forced[k]
