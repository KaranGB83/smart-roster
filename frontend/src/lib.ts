import type { DayStatus, Employee, Pod } from './types'

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

/** Parse a YYYY-MM-DD string as a local date (never via Date(string), which shifts by timezone). */
export const parseISO = (s: string) => {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}
export const toISO = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function monthDays(monthStart: string): string[] {
  const first = parseISO(monthStart)
  const n = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  return Array.from({ length: n }, (_, i) => toISO(new Date(first.getFullYear(), first.getMonth(), i + 1)))
}

export const weekdayShort = (s: string) => WEEKDAYS[parseISO(s).getDay()]
export const dayOfMonth = (s: string) => parseISO(s).getDate()
export const isWeekend = (s: string) => [0, 6].includes(parseISO(s).getDay())
export const fmtDay = (s: string) => {
  const d = parseISO(s)
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`
}
export const fmtMonth = (s: string) => {
  const d = parseISO(s)
  return `${MONTHS_LONG[d.getMonth()]} ${d.getFullYear()}`
}
export const fmtMonthShort = (s: string) => {
  const d = parseISO(s)
  return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}
export const fmtRange = (a: string, b: string) => (a === b ? fmtDay(a) : `${fmtDay(a)} to ${fmtDay(b)}`)
export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`
export const cls = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

export const STATUS: Record<DayStatus, { label: string; glyph: string; cls: string }> = {
  working: { label: 'Working', glyph: '', cls: 'st-working' },
  weekly_off: { label: 'Weekly off', glyph: '', cls: 'st-off' },
  leave: { label: 'Leave', glyph: 'L', cls: 'st-leave' },
  comp_off: { label: 'Comp-off', glyph: 'C', cls: 'st-comp' },
  holiday_off: { label: 'Closed day', glyph: 'H', cls: 'st-hol' },
}

export const isCoverageCode = (code: string) => code === 'NO_COVERAGE' || code === 'UNDER_MIN_STAFF'

export interface PodGroup { key: string; name: string; employees: Employee[] }

export function groupByPod(employees: Employee[], pods: Pod[]): PodGroup[] {
  const names = new Map(pods.map((p) => [p.id, p.name]))
  const groups = new Map<string, PodGroup>()
  for (const e of employees) {
    const key = e.pod_id ?? 'none'
    if (!groups.has(key)) groups.set(key, { key, name: e.pod_id ? (names.get(e.pod_id) ?? 'Pod') : 'No pod', employees: [] })
    groups.get(key)!.employees.push(e)
  }
  const out = [...groups.values()].sort((a, b) => a.name.localeCompare(b.name))
  for (const g of out) {
    g.employees.sort((a, b) => Number(b.is_pod_lead) - Number(a.is_pod_lead) || (a.code ?? '').localeCompare(b.code ?? ''))
  }
  return out
}
