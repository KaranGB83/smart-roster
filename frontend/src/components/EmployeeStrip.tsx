import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { fmtRange, plural } from '../lib'
import type { Assignment, AssignmentDetail, DayStatus, Employee, Entry, Leave, Pod } from '../types'

const DAYS = ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const ORDER: DayStatus[] = ['working', 'weekly_off', 'leave', 'comp_off', 'holiday_off']
const COUNT_LABEL: Record<DayStatus, (n: number) => string> = {
  working: () => 'working',
  weekly_off: () => 'weekly off',
  leave: () => 'on leave',
  comp_off: () => 'comp-off',
  holiday_off: (n) => (n === 1 ? 'closed day' : 'closed days'),
}

export function EmployeeStrip({ employee, pods, details, entries, days }: {
  employee: Employee; pods: Pod[]; details: AssignmentDetail[]; entries: Map<string, Entry>; days: string[]
}) {
  const leaves = useQuery({ queryKey: ['leaves', employee.id], queryFn: () => api.get<Leave[]>(`/leaves?employee_id=${employee.id}`) })
  const assignments = useQuery({ queryKey: ['assignments', employee.id], queryFn: () => api.get<Assignment[]>(`/assignments?employee_id=${employee.id}`) })
  const windows = new Map((assignments.data ?? []).map((a) => [a.brand_process_id, a]))
  const mine = details.filter((d) => d.employee_id === employee.id)
  const counts: Partial<Record<DayStatus, number>> = {}
  for (const d of days) {
    const s = entries.get(`${employee.id}|${d}`)?.status
    if (s) counts[s] = (counts[s] ?? 0) + 1
  }
  const pod = pods.find((p) => p.id === employee.pod_id)?.name
  return (
    <section className="estrip" aria-label={`${employee.full_name} summary`}>
      <div>
        <h2>{employee.full_name}</h2>
        <p>{[employee.code, pod, employee.is_pod_lead ? 'pod lead' : null].filter(Boolean).join(', ')}</p>
      </div>
      <dl>
        <div><dt>Covers</dt><dd>{mine.length ? mine.map((m) => {
          const a = windows.get(m.brand_process_id)
          const temp = a?.effective_from && a.effective_to ? ` (${fmtRange(a.effective_from, a.effective_to)} only)` : ''
          return `${m.brand} ${m.process}${temp}`
        }).join(', ') : 'No assignments'}</dd></div>
        <div><dt>Rules</dt><dd>{plural(employee.weekly_offs_per_week, 'weekly off')} a week, at most {employee.max_consecutive_days} days in a row{employee.preferred_off_days.length > 0 && `, prefers ${employee.preferred_off_days.map((d) => DAYS[d]).join(' and ')} off`}</dd></div>
        <div><dt>This month</dt><dd>{ORDER.filter((k) => counts[k]).map((k) => `${counts[k]} ${COUNT_LABEL[k](counts[k]!)}`).join(', ') || 'No days yet'}</dd></div>
        <div><dt>Leave</dt><dd>{leaves.data && leaves.data.length > 0 ? leaves.data.map((l) => `${fmtRange(l.start_date, l.end_date)} (${l.status})`).join('; ') : 'None recorded'}</dd></div>
      </dl>
    </section>
  )
}
