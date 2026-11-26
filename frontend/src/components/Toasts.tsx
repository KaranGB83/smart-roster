import { CheckIcon, CloseIcon, ErrorIcon, WarnIcon } from '../icons'
import { cls } from '../lib'

export interface Toast { id: number; tone: 'ok' | 'warn' | 'err'; text: string }

export function Toasts({ items, dismiss }: { items: Toast[]; dismiss: (id: number) => void }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={cls('toast', t.tone)}>
          {t.tone === 'ok' ? <CheckIcon /> : t.tone === 'warn' ? <WarnIcon /> : <ErrorIcon />}
          <span>{t.text}</span>
          <button aria-label="Dismiss" onClick={() => dismiss(t.id)}><CloseIcon /></button>
        </div>
      ))}
    </div>
  )
}
