import { useEffect, useRef, useState } from 'react'
import { CheckIcon, ErrorIcon, WarnIcon } from '../icons'
import { cls, fmtMonthShort, plural } from '../lib'
import type { Roster, Summary } from '../types'

interface Props {
  rosters: Roster[]
  roster?: Roster
  summary?: Summary
  generating: boolean
  publishing: boolean
  onSelect: (id: string) => void
  onGenerate: (month: string, name: string) => Promise<void>
  onPublish: () => void
}

function GenerateDialog({ open, defaultMonth, busy, onClose, onGenerate }: {
  open: boolean; defaultMonth: string; busy: boolean; onClose: () => void; onGenerate: (m: string, n: string) => Promise<void>
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [month, setMonth] = useState(defaultMonth)
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) { setMonth(defaultMonth); setErr(''); d.showModal() }
    if (!open && d.open) d.close()
  }, [open, defaultMonth])
  return (
    <dialog ref={ref} className="dlg" onClose={onClose} onCancel={onClose}>
      <form onSubmit={async (e) => {
        e.preventDefault()
        try { await onGenerate(month, name.trim()); onClose() } catch (x) { setErr((x as Error).message) }
      }}>
        <h2>Generate roster</h2>
        <p className="lede">Builds a draft for the whole month from the current people, brands, leave and holidays. Locked days are kept when you base it on an existing roster.</p>
        <label>Month<input type="month" required value={month} onChange={(e) => setMonth(e.target.value)} /></label>
        <label>Name <span className="opt">optional</span><input type="text" value={name} placeholder="For example, Dec plan B" onChange={(e) => setName(e.target.value)} /></label>
        {err && <p className="hint bad" role="alert">{err}</p>}
        <div className="dlg-f">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary" disabled={busy || !month}>{busy ? 'Generating…' : 'Generate roster'}</button>
        </div>
      </form>
    </dialog>
  )
}

export function Header({ rosters, roster, summary, generating, publishing, onSelect, onGenerate, onPublish }: Props) {
  const [dlg, setDlg] = useState(false)
  const now = new Date()
  const next = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  const defaultMonth = roster ? roster.month_start.slice(0, 7) : `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`
  const published = roster?.status === 'published'
  const blocked = !!roster && !!summary && !summary.publishable

  return (
    <header className="top">
      <div className="mark">
        <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="6" fill="currentColor" /><path d="M7 9h18M7 16h18M7 23h18" stroke="var(--surface)" strokeWidth="3" /><rect x="19" y="13" width="6" height="6" fill="var(--crit)" /></svg>
        <span>Roster planner</span>
      </div>

      {rosters.length > 0 && (
        <label className="pick">
          <span className="sr">Roster</span>
          <select value={roster?.id ?? ''} onChange={(e) => onSelect(e.target.value)}>
            {rosters.map((r) => <option key={r.id} value={r.id}>{fmtMonthShort(r.month_start)}, {r.name}</option>)}
          </select>
        </label>
      )}
      {roster && <span className={cls('chip', roster.status)}>{roster.status}</span>}

      {roster && summary && (
        <p className="state" aria-live="polite">
          {summary.errors > 0 && <span className="s bad"><ErrorIcon /> {plural(summary.errors, 'error')}</span>}
          {summary.warnings > 0 && <span className="s warn"><WarnIcon /> {plural(summary.warnings, 'warning')}</span>}
          {summary.publishable && <span className="s good"><CheckIcon /> {published ? 'Published, no errors' : 'Ready to publish'}</span>}
          {blocked && <span className="s muted">Fix {summary.errors === 1 ? 'it' : 'them'} to publish</span>}
        </p>
      )}

      <div className="actions">
        <button className="btn" onClick={() => setDlg(true)}>Generate roster</button>
        <button
          className="btn primary"
          disabled={!roster || blocked || published || roster?.status === 'archived' || publishing}
          title={blocked ? 'Resolve the errors first' : undefined}
          onClick={onPublish}
        >
          {publishing ? 'Publishing…' : published ? 'Published' : 'Publish roster'}
        </button>
      </div>
      <GenerateDialog open={dlg} defaultMonth={defaultMonth} busy={generating} onClose={() => setDlg(false)} onGenerate={(m, n) => onGenerate(m, n)} />
    </header>
  )
}
