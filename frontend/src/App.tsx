import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { CellEditor, type EditTarget } from './components/CellEditor'
import { EmployeeStrip } from './components/EmployeeStrip'
import { Header } from './components/Header'
import { IssuesPanel, WhatIfPanel } from './components/Rail'
import { Legend, Sheet } from './components/Sheet'
import { Toasts, type Toast } from './components/Toasts'
import { cls, fmtMonth, groupByPod, monthDays, plural } from './lib'
import { resolveScope, SCOPE_LABEL, type Focus, type Scope, type ScopeKind } from './scope'
import type {
  AssignmentDetail, Brand, CoverageRow, DayStatus, EditsPayload, Employee, Entry, GenerateResult,
  Holiday, ImpactResult, Issue, LeaveImpact, Pod, Process, Roster, Validation,
} from './types'

/** While refetching the same roster keep the previous render; never show another roster's data. */
function keepSame<T>(rid?: string) {
  return (prev: T | undefined, prevQuery?: { queryKey: readonly unknown[] }) =>
    prevQuery?.queryKey[1] === rid ? prev : undefined
}

const KINDS: ScopeKind[] = ['company', 'pod', 'brand', 'process', 'employee']
const firstSentence = (m: string) => m.split('. ')[0].replace(/\.$/, '')

function describe(label: string, r: ImpactResult) {
  const parts: string[] = []
  if (r.resolved.length) parts.push(`${plural(r.resolved.length, 'problem')} resolved`)
  if (r.introduced.length) parts.push(`${plural(r.introduced.length, 'new problem')}: ${firstSentence(r.introduced[0].message)}`)
  return parts.length ? `${label}. ${parts.join('. ')}.` : `${label}. No new problems.`
}

export default function App() {
  const qc = useQueryClient()
  const employeesQ = useQuery({ queryKey: ['employees'], queryFn: () => api.get<Employee[]>('/employees') })
  const podsQ = useQuery({ queryKey: ['pods'], queryFn: () => api.get<Pod[]>('/pods') })
  const brandsQ = useQuery({ queryKey: ['brands'], queryFn: () => api.get<Brand[]>('/brands') })
  const processesQ = useQuery({ queryKey: ['processes'], queryFn: () => api.get<Process[]>('/processes') })
  const detailsQ = useQuery({ queryKey: ['details'], queryFn: () => api.get<AssignmentDetail[]>('/assignment-details') })
  const holidaysQ = useQuery({ queryKey: ['holidays'], queryFn: () => api.get<Holiday[]>('/holidays') })
  const rostersQ = useQuery({ queryKey: ['rosters'], queryFn: () => api.get<Roster[]>('/rosters') })

  const [rosterId, setRosterId] = useState<string>()
  const roster = rostersQ.data?.find((r) => r.id === rosterId) ?? rostersQ.data?.[0]
  const rid = roster?.id
  const days = useMemo(() => (roster ? monthDays(roster.month_start) : []), [roster])

  const entriesQ = useQuery({
    queryKey: ['entries', rid], enabled: !!rid, placeholderData: keepSame<Entry[]>(rid),
    queryFn: () => api.get<Entry[]>(`/rosters/${rid}/entries`),
  })
  const coverageQ = useQuery({
    queryKey: ['coverage', rid], enabled: !!rid, placeholderData: keepSame<CoverageRow[]>(rid),
    queryFn: () => api.get<CoverageRow[]>(`/rosters/${rid}/coverage`),
  })
  const validationQ = useQuery({
    queryKey: ['validation', rid], enabled: !!rid, placeholderData: keepSame<Validation>(rid),
    queryFn: () => api.post<Validation>(`/rosters/${rid}/validate`),
  })

  const [scope, setScope] = useState<Scope>({ kind: 'company' })
  const [focus, setFocus] = useState<Focus>({})
  const [tab, setTab] = useState<'issues' | 'whatif'>('issues')
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditTarget | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(0)

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const notify = useCallback((text: string, tone: Toast['tone'] = 'ok') => {
    const id = ++toastId.current
    setToasts((t) => [...t, { id, tone, text }])
    setTimeout(() => dismiss(id), tone === 'ok' ? 5000 : 9000)
  }, [dismiss])

  const employees = useMemo(() => (employeesQ.data ?? []).filter((e) => e.is_active), [employeesQ.data])
  const pods = useMemo(() => podsQ.data ?? [], [podsQ.data])
  const details = useMemo(() => detailsQ.data ?? [], [detailsQ.data])
  const coverage = useMemo(() => coverageQ.data ?? [], [coverageQ.data])
  const entries = useMemo(() => new Map((entriesQ.data ?? []).map((e) => [`${e.employee_id}|${e.on_date}`, e])), [entriesQ.data])
  const holidays = useMemo(() => new Map((holidaysQ.data ?? []).map((h) => [h.on_date, h.name])), [holidaysQ.data])
  const scoped = useMemo(() => resolveScope(scope, employees, details, coverage), [scope, employees, details, coverage])
  const groups = useMemo(() => groupByPod(scoped.employees, pods), [scoped.employees, pods])

  const refresh = useCallback(async (id: string) => {
    await Promise.all(['entries', 'coverage', 'validation', 'suggestions'].map((k) => qc.invalidateQueries({ queryKey: [k, id] })))
    qc.invalidateQueries({ queryKey: ['leaves'] })
    qc.invalidateQueries({ queryKey: ['rosters'] })
    qc.invalidateQueries({ queryKey: ['details'] })
    qc.invalidateQueries({ queryKey: ['assignments'] })
  }, [qc])

  const editsM = useMutation({
    mutationFn: (v: { payload: EditsPayload; label: string }) => api.post<ImpactResult>(`/rosters/${rid}/edits`, v.payload),
    onSuccess: (r, v) => {
      notify(describe(v.label, r), r.introduced.some((i) => i.severity === 'error') ? 'warn' : 'ok')
      if (rid) refresh(rid)
    },
    onError: (e: Error) => notify(`Couldn't save. ${e.message}`, 'err'),
  })

  const generateM = useMutation({
    mutationFn: (v: { month: string; name: string }) =>
      api.post<GenerateResult>('/rosters/generate', { month_start: `${v.month}-01`, ...(v.name ? { name: v.name } : {}) }),
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ['rosters'] })
      if (!r.roster) return notify(`No roster could be built. ${r.warnings[0] ?? 'Check locked days and leave.'}`, 'err')
      setRosterId(r.roster.id)
      setFocus({})
      setOpenKey(null)
      notify(r.gap_count === 0 ? `Generated ${fmtMonth(r.roster.month_start)}. Every brand is staffed.` : `Generated ${fmtMonth(r.roster.month_start)}. ${plural(r.gap_count, 'gap')} to review.`, r.gap_count === 0 ? 'ok' : 'warn')
    },
    onError: (e: Error) => notify(e.message, 'err'),
  })

  const publishM = useMutation({
    mutationFn: () => api.patch<Roster>(`/rosters/${rid}`, { status: 'published' }),
    onSuccess: () => { notify('Roster published.'); if (rid) refresh(rid) },
    onError: (e: Error) => notify(`Can't publish. ${e.message}`, 'err'),
  })

  const goTo = (f: Focus) => {
    const missing = (f.bpId && !scoped.coverage.some((r) => r.brand_process_id === f.bpId)) ||
      (f.employeeId && !scoped.employees.some((e) => e.id === f.employeeId))
    if (missing) setScope({ kind: 'company' })
    setFocus(f)
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (f.date) document.getElementById(`day-${f.date}`)?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
      const row = f.bpId ? document.querySelector(`[data-bp="${f.bpId}"]`) : f.employeeId ? document.querySelector(`[data-emp="${f.employeeId}"]`) : null
      row?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' })
    }))
  }

  const onShow = (i: Issue) => goTo({ date: i.on_date ?? undefined, bpId: i.brand_process_id ?? undefined, employeeId: i.brand_process_id ? undefined : (i.employee_id ?? undefined) })
  const onApply = (payload: EditsPayload) => editsM.mutate({ payload, label: 'Fix applied' }, { onSuccess: () => setOpenKey(null) })
  const onRecorded = (r: LeaveImpact) => {
    notify(r.fully_absorbed ? 'Leave recorded. The team absorbs it.' : `Leave recorded. ${plural(r.new_gaps.length, 'gap')} to fix.`, r.fully_absorbed ? 'ok' : 'warn')
    if (rid) refresh(rid)
    setTab('issues')
    const first = r.new_gaps[0]?.issue
    if (first?.brand_process_id && first.on_date) {
      setOpenKey(`${first.brand_process_id}|${first.on_date}`)
      goTo({ date: first.on_date, bpId: first.brand_process_id })
    }
  }

  const options: Record<Exclude<ScopeKind, 'company'>, { id: string; label: string }[]> = {
    pod: pods.map((p) => ({ id: p.id, label: p.name })).sort((a, b) => a.label.localeCompare(b.label)),
    brand: (brandsQ.data ?? []).map((b) => ({ id: b.id, label: b.name })).sort((a, b) => a.label.localeCompare(b.label)),
    process: (processesQ.data ?? []).map((p) => ({ id: p.id, label: `${p.code}, ${p.name}` })),
    employee: [...employees].sort((a, b) => a.full_name.localeCompare(b.full_name)).map((e) => ({ id: e.id, label: e.full_name })),
  }
  const pickKind = (kind: ScopeKind) => setScope(kind === 'company' ? { kind } : { kind, id: options[kind][0]?.id })
  const employee = scope.kind === 'employee' ? employees.find((e) => e.id === scope.id) : undefined

  const readOnly = roster?.status === 'archived'
  const summary = validationQ.data?.summary
  const firstError = employeesQ.error ?? rostersQ.error

  if (firstError) {
    return (
      <div className="state-page">
        <h1>Can't load the roster data</h1>
        <p>{(firstError as Error).message}</p>
        <p className="hint">The planner expects the API at <code>{api.base}</code>. Start the backend with <code>uvicorn app.main:app --reload</code>, and make sure <code>CORS_ORIGINS</code> includes this page's address.</p>
        <button className="btn primary" onClick={() => qc.invalidateQueries()}>Try again</button>
      </div>
    )
  }

  const now = new Date()
  const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  const nextKey = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, '0')}`

  return (
    <div className="app">
      <Header
        rosters={rostersQ.data ?? []}
        roster={roster}
        summary={summary}
        generating={generateM.isPending}
        publishing={publishM.isPending}
        onSelect={(id) => { setRosterId(id); setFocus({}); setOpenKey(null) }}
        onGenerate={async (month, name) => { await generateM.mutateAsync({ month, name }) }}
        onPublish={() => publishM.mutate()}
      />

      {!roster && !rostersQ.isLoading ? (
        <div className="state-page">
          {employees.length === 0 && !employeesQ.isLoading ? (
            <>
              <h1>No people yet</h1>
              <p>Add employees, brands and assignments through the API, or load the sample set with <code>python -m app.seed --reset</code>. Then generate a roster here.</p>
            </>
          ) : (
            <>
              <h1>No roster yet</h1>
              <p>Generate a draft for {fmtMonth(`${nextKey}-01`)} from the {plural(employees.length, 'person', 'people')} in the system. You can edit it and check it before publishing.</p>
              <button className="btn primary" disabled={generateM.isPending} onClick={() => generateM.mutate({ month: nextKey, name: '' })}>
                {generateM.isPending ? 'Generating…' : `Generate ${fmtMonth(`${nextKey}-01`)}`}
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="layout">
          <main className="main">
            <div className="scopebar">
              <div className="seg" role="group" aria-label="View">
                {KINDS.map((k) => (
                  <button key={k} aria-pressed={scope.kind === k} onClick={() => pickKind(k)}>{SCOPE_LABEL[k]}</button>
                ))}
              </div>
              {scope.kind !== 'company' && (
                <label className="pick">
                  <span className="sr">{SCOPE_LABEL[scope.kind]}</span>
                  <select value={scope.id ?? ''} onChange={(e) => setScope({ kind: scope.kind, id: e.target.value })}>
                    {options[scope.kind].map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                </label>
              )}
              <Legend />
            </div>
            {employee && roster && <EmployeeStrip employee={employee} pods={pods} details={details} entries={entries} days={days} />}
            {days.length > 0 && (
              <Sheet
                days={days}
                holidays={holidays}
                coverage={scoped.coverage}
                groups={groups}
                entries={entries}
                focus={focus}
                showGroups={scope.kind !== 'employee' && scope.kind !== 'pod'}
                stale={(entriesQ.isFetching || coverageQ.isFetching) && !!entriesQ.data}
                onCell={(emp, date, el) => {
                  setFocus({ date, employeeId: emp.id })
                  setEditing({ employee: emp, date, rect: el.getBoundingClientRect(), entry: entries.get(`${emp.id}|${date}`) })
                }}
                onCoverage={(row, cell) => {
                  setFocus({ date: cell.on_date, bpId: row.brand_process_id })
                  if (cell.state === 'open' && cell.covered < cell.required) {
                    setTab('issues')
                    setOpenKey(`${row.brand_process_id}|${cell.on_date}`)
                  }
                }}
              />
            )}
          </main>

          <aside className="rail" aria-label="Review">
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === 'issues'} className={cls(tab === 'issues' && 'on')} onClick={() => setTab('issues')}>
                Issues{summary && summary.errors > 0 && <span className="badge">{summary.errors}</span>}
              </button>
              <button role="tab" aria-selected={tab === 'whatif'} className={cls(tab === 'whatif' && 'on')} onClick={() => setTab('whatif')}>
                What if someone is out?
              </button>
            </div>
            <div className="rail-body" role="tabpanel">
              {rid && tab === 'issues' && (
                <IssuesPanel
                  validation={validationQ.data}
                  loading={validationQ.isLoading}
                  rosterId={rid}
                  readOnly={!!readOnly}
                  busy={editsM.isPending}
                  openKey={openKey}
                  setOpenKey={setOpenKey}
                  onShow={onShow}
                  onApply={onApply}
                />
              )}
              {rid && tab === 'whatif' && (
                <WhatIfPanel key={rid} rosterId={rid} days={days} employees={employees} pods={pods} readOnly={!!readOnly} onRecorded={onRecorded} onError={(m) => notify(m, 'err')} />
              )}
            </div>
          </aside>
        </div>
      )}

      {editing && roster && (
        <CellEditor
          target={editing}
          readOnly={!!readOnly}
          busy={editsM.isPending}
          onClose={() => setEditing(null)}
          onSave={(status: DayStatus, locked: boolean) => {
            editsM.mutate({
              payload: { entries: [{ employee_id: editing.employee.id, on_date: editing.date, status, is_locked: locked }], assignments: [] },
              label: 'Saved',
            })
            setEditing(null)
          }}
        />
      )}
      <Toasts items={toasts} dismiss={dismiss} />
    </div>
  )
}
