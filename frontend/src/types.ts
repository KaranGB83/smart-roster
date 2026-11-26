export type DayStatus = 'working' | 'weekly_off' | 'leave' | 'comp_off' | 'holiday_off'
export type RosterStatus = 'draft' | 'published' | 'archived'
export type Severity = 'error' | 'warning' | 'info'

export interface Employee {
  id: string
  code: string | null
  full_name: string
  pod_id: string | null
  is_pod_lead: boolean
  is_active: boolean
  weekly_offs_per_week: number
  max_consecutive_days: number
  preferred_off_days: number[]
}
export interface Pod { id: string; name: string; lead_id: string | null }
export interface Brand { id: string; name: string; is_active: boolean }
export interface Process { id: string; code: string; name: string }
export interface AssignmentDetail {
  assignment_id: string
  employee_id: string
  full_name: string
  pod: string | null
  brand_id: string
  brand: string
  process_id: string
  process: string
  brand_process_id: string
  calendar: string
  min_staff: number
  allocation_pct: number
}
export interface Assignment {
  id: string
  employee_id: string
  brand_process_id: string
  effective_from: string | null
  effective_to: string | null
}
export interface Holiday { id: string; on_date: string; name: string }
export interface Leave {
  id: string
  employee_id: string
  start_date: string
  end_date: string
  type: string
  status: string
  reason: string | null
}

export interface Roster {
  id: string
  month_start: string
  name: string
  status: RosterStatus
  parent_id: string | null
  created_at: string
  published_at: string | null
}
export interface Entry {
  id: string
  roster_id: string
  employee_id: string
  on_date: string
  status: DayStatus
  is_manual: boolean
  is_locked: boolean
}

export interface CoverageCell {
  on_date: string
  state: 'open' | 'closed_holiday' | 'closed_regular'
  required: number
  covered: number
}
export interface CoverageRow {
  brand_process_id: string
  brand: string
  process: string
  label: string
  employee_ids: string[]
  cells: CoverageCell[]
}

export interface Issue {
  code: string
  severity: Severity
  message: string
  on_date: string | null
  brand_process_id: string | null
  employee_id: string | null
  label: string | null
  details: Record<string, unknown>
}
export interface Summary { errors: number; warnings: number; info: number; publishable: boolean }
export interface Validation { summary: Summary; issues: Issue[] }

export interface EditsPayload {
  entries: { employee_id: string; on_date: string; status: DayStatus; is_locked?: boolean }[]
  assignments: {
    employee_id: string
    brand_process_id: string
    effective_from?: string | null
    effective_to?: string | null
  }[]
}
export interface Suggestion {
  kind: string
  title: string
  detail: string
  edits: EditsPayload | null
  errors_before: number
  errors_after: number
  side_effects: string[]
}
export interface ImpactResult { summary: Summary; introduced: Issue[]; resolved: Issue[] }
export interface GapReport { issue: Issue; suggestions: Suggestion[] }
export interface LeaveImpact {
  applied: boolean
  fully_absorbed: boolean
  affected_brands: string[]
  coverage_checks: { label: string; on_date: string; required: number; working: number; ok: boolean }[]
  new_gaps: GapReport[]
  other_errors: Issue[]
  summary: Summary
}
export interface GenerateResult {
  roster: Roster | null
  solver_status: string
  solve_seconds: number
  coverage_slots: number
  gap_count: number
  warning_count: number
  publishable: boolean
  warnings: string[]
}
