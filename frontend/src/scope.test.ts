import { describe, expect, it } from 'vitest'
import { resolveScope } from './scope'
import type { AssignmentDetail, CoverageRow, Employee } from './types'

const emp = (id: string, pod: string): Employee => ({
  id, code: id, full_name: id, pod_id: pod, is_pod_lead: false, is_active: true,
  weekly_offs_per_week: 1, max_consecutive_days: 6, preferred_off_days: [],
})
const det = (employee_id: string, brand_id: string, process_id: string, bp: string): AssignmentDetail => ({
  assignment_id: employee_id + bp, employee_id, full_name: employee_id, pod: null, brand_id, brand: brand_id,
  process_id, process: process_id, brand_process_id: bp, calendar: 'all_365', min_staff: 1, allocation_pct: 100,
})
const row = (bp: string): CoverageRow => ({
  brand_process_id: bp, brand: bp, process: bp, label: bp, employee_ids: [], cells: [],
})

// a, b in pod P1; c in pod P2.  bpX = brand1/CS (a), bpY = brand1/ACC (a, b), bpZ = brand2/CS (c)
const employees = [emp('a', 'P1'), emp('b', 'P1'), emp('c', 'P2')]
const details = [det('a', 'brand1', 'CS', 'bpX'), det('a', 'brand1', 'ACC', 'bpY'), det('b', 'brand1', 'ACC', 'bpY'), det('c', 'brand2', 'CS', 'bpZ')]
const coverage = [row('bpX'), row('bpY'), row('bpZ')]
const ids = (r: ReturnType<typeof resolveScope>) => [r.employees.map((e) => e.id), r.coverage.map((c) => c.brand_process_id)]

describe('resolveScope', () => {
  it('company shows everything', () => {
    expect(ids(resolveScope({ kind: 'company' }, employees, details, coverage))).toEqual([['a', 'b', 'c'], ['bpX', 'bpY', 'bpZ']])
  })
  it('pod shows its people and the lines they cover', () => {
    expect(ids(resolveScope({ kind: 'pod', id: 'P1' }, employees, details, coverage))).toEqual([['a', 'b'], ['bpX', 'bpY']])
  })
  it('brand shows the brand lines and everyone assigned to them', () => {
    expect(ids(resolveScope({ kind: 'brand', id: 'brand1' }, employees, details, coverage))).toEqual([['a', 'b'], ['bpX', 'bpY']])
    expect(ids(resolveScope({ kind: 'brand', id: 'brand2' }, employees, details, coverage))).toEqual([['c'], ['bpZ']])
  })
  it('process shows that process across brands', () => {
    expect(ids(resolveScope({ kind: 'process', id: 'CS' }, employees, details, coverage))).toEqual([['a', 'c'], ['bpX', 'bpZ']])
  })
  it('employee shows one person and their lines', () => {
    expect(ids(resolveScope({ kind: 'employee', id: 'b' }, employees, details, coverage))).toEqual([['b'], ['bpY']])
  })
  it('a scope with no id falls back to the whole company', () => {
    expect(ids(resolveScope({ kind: 'brand' }, employees, details, coverage))[0]).toEqual(['a', 'b', 'c'])
  })
})
