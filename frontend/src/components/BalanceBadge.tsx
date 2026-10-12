import { useDashboard } from '../api/queries'
import { formatFigure } from '../lib/format'
import { FigureTip } from './FigureTip'
import './BalanceBadge.css'

/** Total balance in the corner of the header (v6 `.bal`), shared by all screens except the dashboard. */
export function BalanceBadge() {
  const dashboard = useDashboard()
  const figure = dashboard.data?.balance.total

  if (dashboard.isPending) return <span className="bal bal--skeleton" aria-hidden="true" />
  // The screen works without the badge: on an error, or when the clinic has no accounts, nothing is drawn.
  if (!figure || figure.breakdown.length === 0) return null

  const text = formatFigure(figure)
  return (
    <div className="bal" data-testid="header-balance">
      <FigureTip figure={figure} title="Остаток на счетах" emoji="💰">
        {(triggerProps) => (
          <button {...triggerProps} type="button" className="bal__button" aria-label={`Остаток на счетах, ${text}`}>
            <span className="bal__value">{text}</span>
            <span className="bal__label">на счетах и в кассе</span>
          </button>
        )}
      </FigureTip>
    </div>
  )
}
