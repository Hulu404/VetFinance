import type { ReactNode } from 'react'
import type { Figure } from '../api/types'
import { formatFigure } from '../lib/format'
import { FigureTip } from './FigureTip'
import './KpiCard.css'

export type KpiState = 'loading' | 'error' | 'empty' | 'ready'

interface KpiCardProps {
  label: string
  emoji: string
  variant?: 'accent' | 'default' | 'detailed'
  state: KpiState
  /** Required when state is "ready". */
  figure?: Figure
  testId?: string
  /** Sub-line for the zero value ("на счетах пусто"). Zero is a normal state, not an error. */
  zeroText?: string
  /** Sub-line for the empty state ("счетов пока нет"). */
  emptyText?: string
  /** Extra line under the number with its own tip (a second FigureTip): "комиссия 8 683 ₽". */
  extra?: ReactNode
}

function subline(state: KpiState, figure: Figure | undefined, zeroText?: string, emptyText?: string) {
  if (state === 'error') return { text: 'не загрузилось', tone: 'bad' as const }
  if (state === 'empty') return { text: emptyText ?? 'нет данных', tone: 'soft' as const }
  if (state !== 'ready' || !figure) return null
  if (figure.value < 0) return { text: 'ниже нуля', tone: 'bad' as const }
  if (figure.value === 0 && zeroText) return { text: zeroText, tone: 'soft' as const }
  return null
}

export function KpiCard({ label, emoji, variant = 'default', state, figure, testId, zeroText, emptyText, extra }: KpiCardProps) {
  const className = `kpi kpi--${variant} kpi--${state}${extra ? ' kpi--with-extra' : ''}`
  const hint = subline(state, figure, zeroText, emptyText)

  // The test id is only on a card with data, so e2e waits for the number instead of reading a placeholder.
  if (state === 'loading') {
    return (
      <div className={className}>
        <span className="kpi__emoji" aria-hidden="true">{emoji}</span>
        <div className="kpi__body">
          <span className="kpi__skeleton kpi__skeleton--label" />
          <span className="kpi__skeleton kpi__skeleton--value" />
        </div>
      </div>
    )
  }

  if (state !== 'ready' || !figure) {
    return (
      <div className={className}>
        <span className="kpi__emoji" aria-hidden="true">{emoji}</span>
        <div className="kpi__body">
          <span className="kpi__label">{label}</span>
          <span className="kpi__value">—</span>
          {hint && <span className={`kpi__sub kpi__sub--${hint.tone}`}>{hint.text}</span>}
        </div>
      </div>
    )
  }

  const valueText = formatFigure(figure)
  return (
    <div className={className} data-testid={testId}>
      <FigureTip figure={figure} title={label} emoji={emoji}>
        {(triggerProps) => (
          <button
            {...triggerProps}
            type="button"
            className="kpi__button"
            aria-label={`${label}, ${valueText}`}
          >
            <span className="kpi__emoji" aria-hidden="true">{emoji}</span>
            <span className="kpi__body">
              <span className="kpi__label">{label}</span>
              <span className="kpi__value">{valueText}</span>
              {hint && <span className={`kpi__sub kpi__sub--${hint.tone}`}>{hint.text}</span>}
            </span>
          </button>
        )}
      </FigureTip>
      {extra && <div className="kpi__extra">{extra}</div>}
    </div>
  )
}
