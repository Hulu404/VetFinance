import type { ReactNode } from 'react'
import type { Figure } from '../api/types'
import { formatFigure } from '../lib/format'
import { FigureTip } from './FigureTip'
import './LoadBar.css'

interface LoadBarProps {
  /** Words for the bar itself: "Загрузка 80,0%, занято 104 из 130 часов". */
  barLabel?: string
  name: string
  /** Load of the row as given by the API; null: no hours to compare with. */
  load: Figure | null
  /** Text under the bar ("104 из 130 ч · свободно 26 ч"), built by the screen from the hours of the API. */
  caption: string | null
  /** Words for a screen reader. */
  spoken: string
  /** Shown instead of the bar and the tip when `load` is null. */
  missing?: ReactNode
  testId?: string
  figureKey?: string
}

/** One row of the load: name, percent, the bar and the hours. The whole row opens the tip of `load_pct`. */
export function LoadBar({ barLabel = "", name, load, caption, spoken, missing, testId = 'efficiency-load-pct', figureKey }: LoadBarProps) {
  if (!load) {
    return (
      <div className="loadbar loadbar--empty">
        <div className="loadbar__top">
          <span className="loadbar__name">{name}</span>
          <span className="loadbar__pct">—</span>
        </div>
        <div className="loadbar__track" aria-hidden="true" />
        <div className="loadbar__missing">{missing}</div>
      </div>
    )
  }
  return (
    <div data-testid={testId} data-figure={figureKey}>
      <FigureTip figure={load} title={name} emoji="⏱️">
        {(triggerProps) => (
          <button {...triggerProps} type="button" className="loadbar loadbar--button" aria-label={spoken}>
            <span className="loadbar__top">
              <span className="loadbar__name">{name}</span>
              <span className="loadbar__pct">{formatFigure(load)}</span>
            </span>
            <span className="loadbar__track" role="img" aria-label={barLabel} data-testid="efficiency-load-bar">
              <span className="loadbar__fill" style={{ width: `${Math.min(100, Math.max(0, load.value))}%` }} />
            </span>
            {caption && <span className="loadbar__caption">{caption}</span>}
          </button>
        )}
      </FigureTip>
    </div>
  )
}

export function LoadBarSkeleton() {
  return (
    <div className="loadbar loadbar--skeleton" aria-hidden="true">
      <span className="loadbar__sk loadbar__sk--name" />
      <span className="loadbar__sk loadbar__sk--bar" />
      <span className="loadbar__sk loadbar__sk--caption" />
    </div>
  )
}
