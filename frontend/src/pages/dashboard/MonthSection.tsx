import { Link } from 'react-router-dom'
import type { DashboardMonth, Figure } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { KpiCard } from '../../components/KpiCard'
import { monthNameLower, monthNameTitle, monthOf } from '../../lib/dates'
import { formatDays, formatFigure } from '../../lib/format'
import { DashEmpty } from './DashEmpty'

interface MonthSectionProps {
  month: DashboardMonth
  asOf: string
  dataAsOf: string | null
}

/** Nothing to show yet: the first day of the month, or no data has ever been loaded. */
export function isMonthEmpty(month: DashboardMonth, dataAsOf: string | null): boolean {
  return month.days_passed === 0 || dataAsOf === null
}

function captionOf(month: DashboardMonth, name: string, empty: boolean): string {
  if (month.days_passed === 0) return `${name} только начался`
  if (empty) return name
  return `${name} · ${formatDays(month.days_passed)} из ${month.days_total}`
}

/** Sub-line with its own tip (not the tip of the card). The API leaves the margin out when there is no revenue. */
function MarginLine({ margin }: { margin: Figure }) {
  return (
    <span data-testid="month-margin">
      <span data-testid="month-profit-margin">
        <FigureButton figure={margin} title="Рентабельность" emoji="💰" figureKey="month.profit_margin_pct">
          рентабельность {formatFigure(margin)}
        </FigureButton>
      </span>
    </span>
  )
}

function MonthCards({ month, asOf }: { month: DashboardMonth; asOf: string }) {
  const name = monthNameLower(monthOf(asOf))
  return (
    <ul className="dash-row" data-testid="month-section">
      <li>
        <KpiCard
          testId="month-revenue"
          label="Выручка"
          tipTitle={`Выручка · ${name}`}
          emoji="📈"
          variant="detailed"
          state="ready"
          figure={month.revenue}
          figureKey="month.revenue"
        />
      </li>
      <li>
        <KpiCard
          testId="month-expenses"
          label="Расходы"
          tipTitle={`Расходы · ${name}`}
          emoji="📉"
          variant="detailed"
          state="ready"
          figure={month.expenses}
          figureKey="month.expenses"
        />
      </li>
      <li>
        <KpiCard
          testId="month-profit"
          label="Прибыль"
          tipTitle={`Прибыль · ${name}`}
          emoji="💰"
          variant="detailed"
          state="ready"
          figure={month.profit}
          figureKey="month.profit"
          extra={month.profit_margin_pct ? <MarginLine margin={month.profit_margin_pct} /> : undefined}
        />
      </li>
    </ul>
  )
}

/** "Сентябрь · 9 дней из 30" and the three cards of the month, or a card that asks to load data. */
export function MonthSection({ month, asOf, dataAsOf }: MonthSectionProps) {
  const name = monthNameTitle(monthOf(asOf))
  const empty = isMonthEmpty(month, dataAsOf)
  return (
    <section aria-labelledby="month-caption" className="dash-month">
      <h2 id="month-caption" className="dash-caption" data-testid="month-caption" data-no-tip>
        {captionOf(month, name, empty)}
      </h2>
      {empty ? (
        <DashEmpty
          testId="month-empty"
          icon="📈"
          text={`За ${monthNameLower(monthOf(asOf))} данных пока нет. Загрузите выписку или подключите Ветменеджер: цифры появятся здесь.`}
          actions={
            <>
              <Link className="btn" to="/transactions?import=1">
                Загрузить выписку
              </Link>
              <Link className="btn" to="/settings/connections/vetmanager">
                Подключения
              </Link>
            </>
          }
        />
      ) : (
        <MonthCards month={month} asOf={asOf} />
      )}
    </section>
  )
}
