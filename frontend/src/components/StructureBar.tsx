import type { ReactNode } from 'react'
import type { Figure } from '../api/types'
import { formatFigure } from '../lib/format'
import { FigureButton } from './FigureButton'
import './StructureBar.css'

export interface StructureSegment {
  key: string
  /** Name in the legend. */
  label: string
  /** Share of the whole as given by the API; its value also sets the segment width. Null: shown in the legend only. */
  share: Figure | null
  /** What the legend button opens (the figure of the same row in the table). */
  tip: Figure
  /** Path of the API field for `data-figure`. */
  figureKey: string
  /** 1-based index of `--color-structure-N`. */
  color: number
}

interface StructureBarProps {
  caption: ReactNode
  segments: StructureSegment[]
  /** Words for a screen reader. */
  ariaLabel: string
  testId?: string
  /** Test id of a legend item. */
  itemTestId?: string
}

/** Segments below this share are not drawn (the legend keeps them). */
const MIN_DRAWN_PCT = 0.5
const LIGHT_SEGMENTS = new Set([4, 5])

/**
 * One bar and its legend (design/components.md, section 20). Widths are proportional shares from the API:
 * `flex-grow` does the scaling, so the client adds nothing up.
 */
export function StructureBar({ caption, segments, ariaLabel, testId = 'pnl-structure', itemTestId = 'pnl-structure-item' }: StructureBarProps) {
  const drawn = segments.filter((segment) => segment.share !== null && segment.share.value >= MIN_DRAWN_PCT)
  return (
    <section className="structure" data-testid={testId} aria-label="Структура">
      <h2 className="structure__caption">{caption}</h2>
      <div className="structure__bar" role="img" aria-label={ariaLabel}>
        {drawn.map((segment) => (
          <i
            key={segment.key}
            className={`structure__seg structure__seg--c${segment.color}${LIGHT_SEGMENTS.has(segment.color) ? ' structure__seg--light' : ''}`}
            style={{ flexGrow: segment.share?.value ?? 0 }}
          />
        ))}
      </div>
      <ul className="structure__legend">
        {segments.map((segment) => (
          <li key={segment.key} className="structure__item" data-testid={itemTestId} data-key={segment.key} data-figure={segment.figureKey}>
            <FigureButton
              figure={segment.tip}
              title={segment.label}
              className="structure__btn"
              spokenValue={`${segment.label}, ${formatFigure(segment.share ?? segment.tip)}`}
            >
              <span className={`structure__dot structure__dot--c${segment.color}`} aria-hidden="true" />
              <span className="structure__name">{segment.label}</span>
              <span className="structure__pct">{segment.share ? formatFigure(segment.share) : '—'}</span>
            </FigureButton>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function StructureBarSkeleton() {
  return (
    <section className="structure" aria-hidden="true" data-testid="pnl-structure-loading">
      <div className="structure__bar structure__bar--skeleton" />
      <ul className="structure__legend">
        {Array.from({ length: 6 }, (_, index) => (
          <li key={index} className="structure__skeleton-item" />
        ))}
      </ul>
    </section>
  )
}
