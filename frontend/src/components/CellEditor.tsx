import { useEffect, useRef } from 'react'
import { fmtDay, STATUS } from '../lib'
import type { DayStatus, Employee, Entry } from '../types'

export interface EditTarget { employee: Employee; date: string; rect: DOMRect; entry?: Entry }

interface Props {
  target: EditTarget
  readOnly: boolean
  busy: boolean
  onClose: () => void
  onSave: (status: DayStatus, locked: boolean) => void
}

/** Small popover for changing one day. Leave, comp-off and closed days are not editable here. */
export function CellEditor({ target, readOnly, busy, onClose, onSave }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const { employee, date, entry } = target
  const status = entry?.status
  const editable = !readOnly && (status === 'working' || status === 'weekly_off')
  const locked = entry?.is_locked ?? false

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('button')?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const left = Math.max(8, Math.min(target.rect.left, window.innerWidth - 300))
  const top = Math.min(target.rect.bottom + 6, window.innerHeight - 220)

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div ref={ref} className="pop" role="dialog" aria-label={`Change ${employee.full_name}, ${fmtDay(date)}`} style={{ left, top }}>
        <div className="pop-h">
          <strong>{employee.full_name}</strong>
          <span>{fmtDay(date)}: {status ? STATUS[status].label.toLowerCase() : 'no entry'}</span>
        </div>
        {editable && status ? (
          <div className="pop-b">
            {status === 'working' ? (
              <button className="btn" disabled={busy} onClick={() => onSave('weekly_off', locked)}>Set to weekly off</button>
            ) : (
              <button className="btn" disabled={busy} onClick={() => onSave('working', locked)}>Set to working</button>
            )}
            <button className="btn ghost" disabled={busy} onClick={() => onSave(status, !locked)}>
              {locked ? 'Unlock this day' : 'Lock this day'}
            </button>
            <p className="hint">Locked days stay as they are when you generate the roster again.</p>
          </div>
        ) : (
          <div className="pop-b">
            <p className="hint">
              {readOnly
                ? 'This roster is archived, so it cannot be changed.'
                : status === 'holiday_off'
                  ? 'None of this person’s brands are open this day, so it is a closed day.'
                  : 'This day comes from recorded leave. Use “What if someone is out?” to record or compare changes.'}
            </p>
            <button className="btn ghost" onClick={onClose}>Close</button>
          </div>
        )}
      </div>
    </>
  )
}
