import { describe, expect, it } from 'vitest'
import { fmtDay, fmtMonth, fmtRange, groupByPod, isCoverageCode, isWeekend, monthDays, parseISO, plural, toISO, weekdayShort } from './lib'
import type { Employee, Pod } from './types'

const emp = (over: Partial<Employee>): Employee => ({
  id: 'x', code: null, full_name: 'X', pod_id: null, is_pod_lead: false, is_active: true,
  weekly_offs_per_week: 1, max_consecutive_days: 6, preferred_off_days: [], ...over,
})

describe('dates', () => {
  it('lists every day of a month, including February and leap years', () => {
    const dec = monthDays('2026-12-01')
    expect(dec).toHaveLength(31)
    expect([dec[0], dec[30]]).toEqual(['2026-12-01', '2026-12-31'])
    expect(monthDays('2027-02-01')).toHaveLength(28)
    expect(monthDays('2028-02-01')).toHaveLength(29)
  })

  it('round-trips ISO dates without timezone drift', () => {
    for (const d of monthDays('2026-03-01')) expect(toISO(parseISO(d))).toBe(d)
  })

  it('knows weekdays and weekends', () => {
    expect(weekdayShort('2026-12-01')).toBe('Tue')
    expect(isWeekend('2026-12-05')).toBe(true) // Saturday
    expect(isWeekend('2026-12-06')).toBe(true) // Sunday
    expect(isWeekend('2026-12-07')).toBe(false)
  })

  it('formats for display', () => {
    expect(fmtDay('2026-12-09')).toBe('Wed 9 Dec')
    expect(fmtMonth('2026-12-01')).toBe('December 2026')
    expect(fmtRange('2026-12-09', '2026-12-09')).toBe('Wed 9 Dec')
    expect(fmtRange('2026-12-09', '2026-12-11')).toBe('Wed 9 Dec to Fri 11 Dec')
  })
})

describe('helpers', () => {
  it('pluralises', () => {
    expect(plural(1, 'error')).toBe('1 error')
    expect(plural(2, 'error')).toBe('2 errors')
    expect(plural(0, 'person', 'people')).toBe('0 people')
  })

  it('treats only coverage codes as fixable gaps', () => {
    expect(isCoverageCode('NO_COVERAGE')).toBe(true)
    expect(isCoverageCode('UNDER_MIN_STAFF')).toBe(true)
    expect(isCoverageCode('MAX_CONSECUTIVE')).toBe(false)
  })

  it('groups people by pod: pods by name, leads first, unassigned last-resort group', () => {
    const pods: Pod[] = [{ id: 'b', name: 'Pod Bravo', lead_id: null }, { id: 'a', name: 'Pod Alpha', lead_id: null }]
    const groups = groupByPod([
      emp({ id: '1', code: 'E2', pod_id: 'a' }),
      emp({ id: '2', code: 'E1', pod_id: 'a' }),
      emp({ id: '3', code: 'E3', pod_id: 'a', is_pod_lead: true }),
      emp({ id: '4', code: 'E4', pod_id: 'b' }),
      emp({ id: '5', code: 'E5', pod_id: null }),
    ], pods)
    expect(groups.map((g) => g.name)).toEqual(['No pod', 'Pod Alpha', 'Pod Bravo'])
    expect(groups.find((g) => g.name === 'Pod Alpha')!.employees.map((e) => e.id)).toEqual(['3', '2', '1'])
  })
})
