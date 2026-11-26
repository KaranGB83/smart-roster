import { useRef, useState, type CSSProperties, type FocusEvent, type KeyboardEvent } from 'react'
import { ChevronIcon } from '../icons'
import { cls, dayOfMonth, fmtDay, isWeekend, plural, STATUS, weekdayShort, type PodGroup } from '../lib'
import type { Focus } from '../scope'
import type { CoverageCell, CoverageRow, Employee, Entry } from '../types'

interface Props {
  days: string[]
  holidays: Map<string, string>
  coverage: CoverageRow[]
  groups: PodGroup[]
  entries: Map<string, Entry>
  focus: Focus
  showGroups: boolean
  stale: boolean
  onCell: (employee: Employee, date: string, el: HTMLElement) => void
  onCoverage: (row: CoverageRow, cell: CoverageCell) => void
}

const isShort = (c: CoverageCell) => c.state === 'open' && c.covered < c.required

function personTip(e: Employee, date: string, en?: Entry) {
  if (!en) return `No entry yet\n${e.full_name}, ${fmtDay(date)}`
  const notes = [STATUS[en.status].label]
  if (en.is_locked) notes.push('locked, regeneration keeps it')
  else if (en.is_manual) notes.push('edited by hand')
  return `${notes.join(', ')}\n${e.full_name}, ${fmtDay(date)}`
}

function coverageTip(row: CoverageRow, c: CoverageCell) {
  const when = fmtDay(c.on_date)
  if (c.state === 'closed_holiday') return `Closed for a public holiday\n${row.label}, ${when}`
  if (c.state === 'closed_regular') return `Closed\n${row.label}, ${when}`
  if (isShort(c)) return `${c.covered} of ${c.required} needed. Select to see fixes\n${row.label}, ${when}`
  return `${c.covered} working, ${c.required} needed\n${row.label}, ${when}`
}

export function Legend() {
  return (
    <ul className="legend" aria-label="Legend">
      <li><i className="sw st-working" />Working</li>
      <li><i className="sw st-off" />Weekly off</li>
      <li><i className="sw st-leave">L</i>Leave</li>
      <li><i className="sw st-comp">C</i>Comp-off</li>
      <li><i className="sw st-hol">H</i>Closed day</li>
      <li><i className="sw cv-short">0/1</i>Short</li>
      <li><i className="sw lockmark st-working" />Locked</li>
    </ul>
  )
}

export function Sheet({ days, holidays, coverage, groups, entries, focus, showGroups, stale, onCell, onCoverage }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const lastTab = useRef<Record<string, HTMLElement>>({})
  const [open, setOpen] = useState({ cov: true, ppl: true })
  const [allLines, setAllLines] = useState(false)
  const [tip, setTip] = useState<{ x: number; y: number; title: string; body: string } | null>(null)

  const shortPerDay = days.map((_, i) => coverage.reduce((n, r) => n + (r.cells[i] && isShort(r.cells[i]) ? 1 : 0), 0))
  const shortTotal = shortPerDay.reduce((a, b) => a + b, 0)
  const shortLines = coverage.filter((r) => r.cells.some(isShort))
  const bigView = coverage.length > 12
  const visible = bigView && !allLines ? shortLines : coverage
  const peopleCount = groups.reduce((n, g) => n + g.employees.length, 0)

  const showTip = (el: Element, x: number, y: number) => {
    const raw = el.getAttribute('data-tip')
    if (!raw) return setTip(null)
    const [title, ...rest] = raw.split('\n')
    setTip({ x, y, title, body: rest.join(' ') })
  }

  const onFocus = (e: FocusEvent<HTMLDivElement>) => {
    const el = e.target as HTMLElement
    const g = el.dataset.g
    if (g) {
      const prev = lastTab.current[g]
      if (prev && prev !== el) prev.tabIndex = -1
      el.tabIndex = 0
      lastTab.current[g] = el
    }
    const t = el.closest('[data-tip]')
    if (t) {
      const r = t.getBoundingClientRect()
      showTip(t, r.left + r.width / 2, r.bottom)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const el = e.target as HTMLElement
    const g = el.dataset.g
    if (!g) return
    let r = Number(el.dataset.r)
    let c = Number(el.dataset.c)
    switch (e.key) {
      case 'ArrowRight': c++; break
      case 'ArrowLeft': c--; break
      case 'ArrowDown': r++; break
      case 'ArrowUp': r--; break
      case 'Home': c = 0; break
      case 'End': c = days.length - 1; break
      case 'Enter':
      case ' ':
        e.preventDefault()
        el.click()
        return
      default: return
    }
    e.preventDefault()
    rootRef.current?.querySelector<HTMLElement>(`[data-g="${g}"][data-r="${r}"][data-c="${c}"]`)?.focus()
  }

  const style = { '--days': days.length } as CSSProperties
  let personRow = -1

  return (
    <div className={cls('sheet-wrap', stale && 'is-stale')}>
      <div
        ref={rootRef}
        className="sheet"
        style={style}
        role="grid"
        aria-label="Roster"
        aria-rowcount={coverage.length + peopleCount}
        onFocus={onFocus}
        onBlur={() => setTip(null)}
        onKeyDown={onKeyDown}
        onPointerLeave={() => setTip(null)}
        onPointerMove={(e) => {
          const t = (e.target as HTMLElement).closest('[data-tip]')
          if (t) showTip(t, e.clientX, e.clientY)
          else setTip(null)
        }}
      >
        <div className="row hdr" role="row">
          <div className="lbl corner" role="columnheader">{plural(days.length, 'day')}</div>
          {days.map((d) => {
            const hol = holidays.get(d)
            return (
              <div
                key={d}
                id={`day-${d}`}
                role="columnheader"
                className={cls('dh', isWeekend(d) && 'we', hol && 'hol', focus.date === d && 'is-focus')}
                title={hol ? `${fmtDay(d)}: ${hol}` : fmtDay(d)}
              >
                <span className="dw">{weekdayShort(d).slice(0, 1)}</span>
                <span className="dn">{dayOfMonth(d)}</span>
              </div>
            )
          })}
        </div>

        <div className="band">
          <span className="bandwrap">
            <button className="bandbtn" aria-expanded={open.cov} onClick={() => setOpen((o) => ({ ...o, cov: !o.cov }))}>
              <ChevronIcon className={cls('chev', open.cov && 'down')} />
              <b>Coverage</b>
              <span className={cls('bandnote', shortTotal > 0 && 'bad')}>
                {coverage.length === 0 ? 'no lines in this view' : shortTotal === 0 ? `${plural(coverage.length, 'line')}, all staffed` : `${plural(shortTotal, 'short day')} across ${plural(shortLines.length, 'line')}`}
              </span>
            </button>
            {bigView && open.cov && (
              <button className="bandlink" onClick={() => setAllLines((v) => !v)}>
                {allLines ? 'Show only short lines' : `Show all ${coverage.length} lines`}
              </button>
            )}
          </span>
        </div>

        {open.cov && coverage.length > 0 && (
          <>
            {shortTotal > 0 && (
              <div className="row sum" role="row">
                <div className="lbl" role="rowheader">Short lines per day</div>
                {shortPerDay.map((n, i) => (
                  <div key={days[i]} role="gridcell" className={cls('cv sumcell', isWeekend(days[i]) && 'we', days[i] === focus.date && 'fc', n > 0 && 'has')}>
                    {n > 0 ? n : ''}
                  </div>
                ))}
              </div>
            )}
            {visible.map((row, r) => (
              <div key={row.brand_process_id} role="row" data-bp={row.brand_process_id} className={cls('row', 'cov', focus.bpId === row.brand_process_id && 'is-focus')}>
                <div className="lbl" role="rowheader" title={row.label}>
                  <span className="b">{row.brand}</span>
                  <span className="p">{row.process}</span>
                </div>
                {row.cells.map((c, i) => {
                  const short = isShort(c)
                  const tipText = coverageTip(row, c)
                  return (
                    <div
                      key={c.on_date}
                      role="gridcell"
                      tabIndex={r === 0 && i === 0 ? 0 : -1}
                      data-g="cov" data-r={r} data-c={i}
                      data-tip={tipText}
                      aria-label={tipText.replace('\n', ', ')}
                      className={cls(
                        'cv',
                        c.state !== 'open' ? 'cv-closed' : short ? 'cv-short' : 'cv-ok',
                        isWeekend(c.on_date) && 'we',
                        focus.date === c.on_date && 'fc',
                        focus.date === c.on_date && focus.bpId === row.brand_process_id && 'is-target',
                      )}
                      onClick={() => onCoverage(row, c)}
                    >
                      {short ? `${c.covered}/${c.required}` : ''}
                    </div>
                  )
                })}
              </div>
            ))}
          </>
        )}

        {open.cov && coverage.length > 0 && visible.length === 0 && (
          <div className="band quiet"><span className="gwrap">Every line is staffed on every open day.</span></div>
        )}

        <div className="band">
          <button className="bandbtn bandbtn-solo" aria-expanded={open.ppl} onClick={() => setOpen((o) => ({ ...o, ppl: !o.ppl }))}>
            <ChevronIcon className={cls('chev', open.ppl && 'down')} />
            <b>People</b>
            <span className="bandnote">{peopleCount === 0 ? 'nobody in this view' : `${plural(peopleCount, 'person', 'people')}. Select a day to change it`}</span>
          </button>
        </div>

        {open.ppl && groups.map((g) => (
          <div key={g.key} role="rowgroup">
            {showGroups && (
              <div className="band grp"><span className="gwrap"><span className="gname">{g.name}</span><span className="gcount">{g.employees.length}</span></span></div>
            )}
            {g.employees.map((emp) => {
              const r = ++personRow
              return (
                <div key={emp.id} role="row" data-emp={emp.id} className={cls('row', 'ppl', focus.employeeId === emp.id && 'is-focus')}>
                  <div className="lbl" role="rowheader" title={`${emp.full_name}${emp.code ? ` (${emp.code})` : ''}`}>
                    <span className="b">{emp.full_name}</span>
                    {emp.is_pod_lead && <span className="p">lead</span>}
                  </div>
                  {days.map((d, i) => {
                    const en = entries.get(`${emp.id}|${d}`)
                    const st = en ? STATUS[en.status] : null
                    const tipText = personTip(emp, d, en)
                    return (
                      <div
                        key={d}
                        role="gridcell"
                        tabIndex={r === 0 && i === 0 ? 0 : -1}
                        data-g="ppl" data-r={r} data-c={i}
                        data-tip={tipText}
                        aria-label={tipText.replace('\n', ', ')}
                        className={cls(
                          'cell',
                          st ? st.cls : 'st-none',
                          isWeekend(d) && 'we',
                          en?.is_locked && 'locked',
                          focus.date === d && 'fc',
                          focus.date === d && focus.employeeId === emp.id && 'is-target',
                        )}
                        onClick={(ev) => onCell(emp, d, ev.currentTarget)}
                      >
                        {st?.glyph}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        ))}
      </div>

      {tip && (
        <div
          className="tip"
          role="tooltip"
          style={{ left: Math.min(tip.x + 12, window.innerWidth - 270), top: Math.min(tip.y + 16, window.innerHeight - 70) }}
        >
          <strong>{tip.title}</strong>
          <span>{tip.body}</span>
        </div>
      )}
    </div>
  )
}
