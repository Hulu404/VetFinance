import type { ReactNode } from 'react'
import { Pill, type PillVariant } from './Pill'
import './ConnectionStatus.css'

export type ConnectionTone = 'off' | 'ok' | 'running' | 'stale' | 'failed' | 'partial'

interface ConnectionStatusProps {
  name: string
  meta: string
  tone: ConnectionTone
  /** Text on the right: "обновлено сегодня в 04:12". */
  statusText: string
  pill?: { text: string; variant: PillVariant } | null
  /** Placeholder instead of the status text while connections load. */
  loading?: boolean
  action?: ReactNode
  testId?: string
}

/** Dot, name, meta and status in words; the dot is decoration (design/components.md, section 13). */
export function ConnectionStatus({ name, meta, tone, statusText, pill, loading = false, action, testId }: ConnectionStatusProps) {
  return (
    <div className="cstat" data-testid={testId}>
      <span className={`cstat__dot cstat__dot--${tone}`} aria-hidden="true" />
      <div className="cstat__name">
        <span className="cstat__title">{name}</span>
        <span className="cstat__meta">{meta}</span>
      </div>
      <div className="cstat__right">
        {loading ? (
          <span className="cstat__skeleton" aria-hidden="true" />
        ) : (
          <span className={`cstat__text cstat__text--${tone}`} aria-live="polite">
            {statusText}
          </span>
        )}
        {!loading && pill && <Pill variant={pill.variant}>{pill.text}</Pill>}
        {action}
      </div>
    </div>
  )
}
