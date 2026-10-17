import type { Figure, ObligationStatus } from '../api/types'
import { formatFigure } from '../lib/format'
import { FigureButton } from './FigureButton'
import { Pill } from './Pill'
import './PaidProgress.css'

const FULL_PCT = 100

interface PaidProgressProps {
  /** `paid_pct` of the loan or the lease. */
  figure: Figure
  status: ObligationStatus
  figureKey?: string
  title?: string
  testId?: string
  /** `data-testid` of the "выплачен" pill of a paid-off loan (e2e). */
  pillTestId?: string
}

/** How much of a loan or a lease is paid: the track and the caption in words (design/components.md, section 27). */
export function PaidProgress({ figure, status, figureKey, title = 'Выплачено', testId, pillTestId }: PaidProgressProps) {
  const paidOff = status === 'paid'
  const shown = formatFigure(figure)
  // The width of the bar is a drawing of the number the API gave.
  const width = paidOff ? FULL_PCT : Math.min(FULL_PCT, Math.max(0, figure.value))
  return (
    <div className="paid" data-testid={testId}>
      <div className="paid__track" role="img" aria-label={`Выплачено ${shown}`}>
        <div className="paid__fill" style={{ width: `${width}%` }} />
      </div>
      <div className="paid__caption">
        {paidOff ? (
          <span data-testid={pillTestId} data-status={pillTestId ? status : undefined}>
            <Pill variant="neutral">выплачен</Pill>
          </span>
        ) : (
          <>
            <FigureButton figure={figure} title={title} figureKey={figureKey} spokenValue={`Выплачено ${shown}`}>
              {shown}
            </FigureButton>{' '}
            выплачено
          </>
        )}
      </div>
    </div>
  )
}
