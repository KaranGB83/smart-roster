import type { AssignmentDetail, CoverageRow, Employee } from './types'

export type ScopeKind = 'company' | 'pod' | 'brand' | 'process' | 'employee'
export interface Scope { kind: ScopeKind; id?: string }
export interface Focus { date?: string; bpId?: string; employeeId?: string }

export const SCOPE_LABEL: Record<ScopeKind, string> = {
  company: 'Company',
  pod: 'Pod',
  brand: 'Brand',
  process: 'Process',
  employee: 'Employee',
}

/** Which employees and brand-process lines does a view show? */
export function resolveScope(
  scope: Scope,
  employees: Employee[],
  details: AssignmentDetail[],
  coverage: CoverageRow[],
): { employees: Employee[]; coverage: CoverageRow[] } {
  const byEmp = new Map<string, Set<string>>()
  for (const d of details) {
    if (!byEmp.has(d.employee_id)) byEmp.set(d.employee_id, new Set())
    byEmp.get(d.employee_id)!.add(d.brand_process_id)
  }
  if (scope.kind === 'company' || !scope.id) return { employees, coverage }

  let bpIds = new Set<string>()
  let people: Employee[] = []
  if (scope.kind === 'pod') {
    people = employees.filter((e) => e.pod_id === scope.id)
    for (const e of people) byEmp.get(e.id)?.forEach((b) => bpIds.add(b))
  } else if (scope.kind === 'employee') {
    people = employees.filter((e) => e.id === scope.id)
    bpIds = new Set(byEmp.get(scope.id) ?? [])
  } else {
    const key = scope.kind === 'brand' ? 'brand_id' : 'process_id'
    bpIds = new Set(details.filter((d) => d[key] === scope.id).map((d) => d.brand_process_id))
    const ids = new Set(details.filter((d) => bpIds.has(d.brand_process_id)).map((d) => d.employee_id))
    people = employees.filter((e) => ids.has(e.id))
  }
  return { employees: people, coverage: coverage.filter((r) => bpIds.has(r.brand_process_id)) }
}
