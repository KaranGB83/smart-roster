import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { CheckIcon, ChevronIcon, ErrorIcon, InfoIcon, WarnIcon } from '../icons'
import { cls, fmtDay, groupByPod, isCoverageCode, plural } from '../lib'
import type { EditsPayload, Employee, Issue, LeaveImpact, Pod, Severity, Suggestion, Validation } from '../types'

/** First sentence is the headline, the rest is guidance. */
function splitMessage(msg: string): [string, string] {
  const m = /[.;] /.exec(msg)
  return m ? [msg.slice(0, m.index), msg.slice(m.index + 2)] : [msg.replace(/\.$/, ''), '']
}

const SevIcon = ({ sev }: { sev: Severity }) =>
  sev === 'error' ? <ErrorIcon className="sev error" aria-label="Error" /> : sev === 'warning' ? <WarnIcon className="sev warning" aria-label="Warning" /> : <InfoIcon className="sev info" aria-label="Note" />

export function SuggestionList({ items, onApply, busy }: { items: Suggestion[]; onApply?: (e: EditsPayload) => void; busy?: boolean }) {
  return (
    <ul className="sugs">
      {items.map((s, i) => (
        <li key={i} className={cls('sug', !s.edits && 'esc')}>
          <strong>{s.title}</strong>
          <p>{s.detail}</p>
          {s.side_effects[0] && <p className="side"><WarnIcon /> {s.side_effects[0]}</p>}
          {s.edits && (
            <div className="sug-f">
              <span className="chk"><CheckIcon /> Checked: no new errors</span>
              {onApply && <button className="btn primary sm" disabled={busy} onClick={() => onApply(s.edits!)}>Apply fix</button>}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

function Fixes({ rosterId, bpId, date, onApply, busy }: { rosterId: string; bpId: string; date: string; onApply: (e: EditsPayload) => void; busy: boolean }) {
  const q = useQuery({
    queryKey: ['suggestions', rosterId, bpId, date],
    queryFn: () => api.post<Suggestion[]>(`/rosters/${rosterId}/suggestions`, { brand_process_id: bpId, on_date: date, limit: 4 }),
  })
  if (q.isLoading) return <p className="hint">Checking who could cover this day…</p>
  if (q.error) return <p className="hint bad">{(q.error as Error).message}</p>
  return <SuggestionList items={q.data ?? []} onApply={onApply} busy={busy} />
}

interface IssuesProps {
  validation?: Validation
  loading: boolean
  rosterId: string
  readOnly: boolean
  busy: boolean
  openKey: string | null
  setOpenKey: (k: string | null) => void
  onShow: (i: Issue) => void
  onApply: (e: EditsPayload) => void
}

function IssueItem({ issue, p }: { issue: Issue; p: IssuesProps }) {
  const cov = isCoverageCode(issue.code) && issue.brand_process_id && issue.on_date
  const key = cov ? `${issue.brand_process_id}|${issue.on_date}` : null
  const expanded = key !== null && p.openKey === key
  const ref = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (expanded) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [expanded])
  const [head, rest] = splitMessage(issue.message)
  return (
    <li ref={ref} className={cls('issue', issue.severity, expanded && 'open')}>
      <div className="issue-h">
        <SevIcon sev={issue.severity} />
        <div className="issue-t">
          <button className="issue-msg" onClick={() => p.onShow(issue)}>{head}</button>
          {rest && <span className="issue-meta">{rest}</span>}
        </div>
      </div>
      {key && (
        <button className="btn sm" aria-expanded={expanded} disabled={p.readOnly && !expanded} onClick={() => p.setOpenKey(expanded ? null : key)}>
          {expanded ? 'Hide fixes' : 'Show fixes'}
        </button>
      )}
      {expanded && issue.brand_process_id && issue.on_date && (
        <Fixes rosterId={p.rosterId} bpId={issue.brand_process_id} date={issue.on_date} onApply={p.onApply} busy={p.busy || p.readOnly} />
      )}
    </li>
  )
}

export function IssuesPanel(p: IssuesProps) {
  const [notes, setNotes] = useState(false)
  const issues = p.validation?.issues ?? []
  const by = (s: Severity) => issues.filter((i) => i.severity === s)
  const errors = by('error')
  const warnings = by('warning')
  const infos = by('info')

  if (p.loading && !p.validation) return <p className="rail-empty">Checking every rule…</p>
  return (
    <div className="issues">
      <section>
        <h3>Errors <span className={cls('count', errors.length > 0 && 'bad')}>{errors.length}</span></h3>
        {errors.length === 0 ? (
          <p className="allgood"><CheckIcon /> No errors. Every brand is staffed on every open day.</p>
        ) : (
          <ul className="issue-list">{errors.map((i, n) => <IssueItem key={`${i.code}${i.on_date}${i.employee_id}${n}`} issue={i} p={p} />)}</ul>
        )}
      </section>
      <section>
        <h3>Warnings <span className="count">{warnings.length}</span></h3>
        {warnings.length === 0 ? <p className="hint">Nothing to review.</p> : (
          <ul className="issue-list">{warnings.map((i, n) => <IssueItem key={`${i.code}${i.on_date}${i.employee_id}${n}`} issue={i} p={p} />)}</ul>
        )}
      </section>
      <section>
        <h3>
          <button className="fold" aria-expanded={notes} onClick={() => setNotes(!notes)}>
            <ChevronIcon className={cls('chev', notes && 'down')} /> Notes <span className="count">{infos.length}</span>
          </button>
        </h3>
        {notes && <ul className="issue-list">{infos.map((i, n) => <IssueItem key={`${i.code}${i.brand_process_id}${n}`} issue={i} p={p} />)}</ul>}
        {!notes && infos.length > 0 && <p className="hint">Brands that depend on one person. Open to review.</p>}
      </section>
    </div>
  )
}

interface WhatIfProps {
  rosterId: string
  days: string[]
  employees: Employee[]
  pods: Pod[]
  readOnly: boolean
  onRecorded: (r: LeaveImpact) => void
  onError: (msg: string) => void
}

export function WhatIfPanel({ rosterId, days, employees, pods, readOnly, onRecorded, onError }: WhatIfProps) {
  const [employeeId, setEmployeeId] = useState('')
  const [from, setFrom] = useState(days[8] ?? days[0])
  const [to, setTo] = useState(days[8] ?? days[0])
  const [type, setType] = useState('planned_leave')
  const [result, setResult] = useState<LeaveImpact | null>(null)
  const groups = useMemo(() => groupByPod(employees, pods), [employees, pods])

  const body = { employee_id: employeeId, start_date: from, end_date: to, type }
  const check = useMutation({
    mutationFn: () => api.post<LeaveImpact>(`/rosters/${rosterId}/leave-change`, { ...body, dry_run: true }),
    onSuccess: setResult,
    onError: (e: Error) => onError(e.message),
  })
  const record = useMutation({
    mutationFn: () => api.post<LeaveImpact>(`/rosters/${rosterId}/leave-change`, { ...body, dry_run: false }),
    onSuccess: (r) => { setResult(null); onRecorded(r) },
    onError: (e: Error) => onError(e.message),
  })
  const valid = employeeId !== '' && from !== '' && to !== '' && to >= from
  const reset = () => setResult(null)

  return (
    <form className="whatif" onSubmit={(e) => { e.preventDefault(); if (valid) check.mutate() }}>
      <p className="lede">Pick someone and the days they will be out. You see what breaks before anything is saved.</p>
      <label>Person
        <select value={employeeId} onChange={(e) => { setEmployeeId(e.target.value); reset() }}>
          <option value="">Choose a person</option>
          {groups.map((g) => (
            <optgroup key={g.key} label={g.name}>
              {g.employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
      <div className="two">
        <label>From
          <input type="date" value={from} min={days[0]} max={days[days.length - 1]} onChange={(e) => { setFrom(e.target.value); if (e.target.value > to) setTo(e.target.value); reset() }} />
        </label>
        <label>To
          <input type="date" value={to} min={from} max={days[days.length - 1]} onChange={(e) => { setTo(e.target.value); reset() }} />
        </label>
      </div>
      <label>Type
        <select value={type} onChange={(e) => { setType(e.target.value); reset() }}>
          <option value="planned_leave">Planned leave</option>
          <option value="sick_leave">Sick leave</option>
          <option value="comp_off">Comp-off</option>
        </select>
      </label>
      <button className="btn primary" type="submit" disabled={!valid || check.isPending}>{check.isPending ? 'Checking…' : 'Check impact'}</button>

      {result && (
        <div className={cls('impact', result.fully_absorbed ? 'ok' : 'bad')} aria-live="polite">
          {result.fully_absorbed ? (
            <>
              <h3><CheckIcon /> The team absorbs this</h3>
              <p>Every brand this person covers stays staffed from {fmtDay(from)}{to !== from && ` to ${fmtDay(to)}`}.</p>
            </>
          ) : (
            <>
              <h3><ErrorIcon /> This leaves {plural(result.new_gaps.length, 'gap')}</h3>
              <p>Affects {result.affected_brands.join(', ') || 'the roster'}.</p>
              {result.new_gaps.map((g, i) => (
                <div key={i} className="gap">
                  <strong>{splitMessage(g.issue.message)[0]}</strong>
                  <p className="hint">Options once recorded:</p>
                  <SuggestionList items={g.suggestions.slice(0, 2)} />
                </div>
              ))}
              {result.other_errors.map((o, i) => <p key={i} className="hint bad">{splitMessage(o.message)[0]}</p>)}
            </>
          )}
          <button type="button" className="btn" disabled={readOnly || record.isPending} onClick={() => record.mutate()}>
            {record.isPending ? 'Recording…' : 'Record leave'}
          </button>
          {!result.fully_absorbed && <p className="hint">Gaps then appear under Issues, where you can apply a fix.</p>}
        </div>
      )}
    </form>
  )
}
