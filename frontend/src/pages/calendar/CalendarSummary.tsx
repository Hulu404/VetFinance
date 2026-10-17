import type { CalendarReport } from '../../api/types'
import { KpiCard } from '../../components/KpiCard'
import { formatDayMonth } from '../../lib/dates'
import { isRedDay, paymentsCountText, RED_DAY_WORDS } from '../../lib/planning'

/** The three cards over the calendar: what comes in, what goes out, the lowest balance (design/screens/calendar.md). */
export function CalendarSummary({ summary }: { summary: CalendarReport['summary'] }) {
  const lowestRed = isRedDay(summary.lowest.status)
  const lowestDate = formatDayMonth(summary.lowest.date)
  return (
    <ul className="kpi-grid kpi-grid--plan" aria-label="Итоги окна">
      <li>
        <KpiCard
          label="Поступит за 22 дня"
          emoji="📥"
          state="ready"
          figure={summary.income}
          figureKey="summary.income"
          valueTestId="calendar-income"
          subText="прогноз выручки"
        />
      </li>
      <li>
        <KpiCard
          label="Спишется"
          emoji="📤"
          state="ready"
          figure={summary.expense}
          figureKey="summary.expense"
          valueTestId="calendar-expense"
          subText={paymentsCountText(summary.payments_count)}
          subTestId="calendar-payments-count"
        />
      </li>
      <li data-status={summary.lowest.status}>
        <KpiCard
          label="Самый низкий остаток"
          emoji="📉"
          state="ready"
          figure={summary.lowest.balance}
          figureKey="summary.lowest.balance"
          valueTestId="calendar-lowest"
          valueData={{ 'data-status': summary.lowest.status }}
          subText={lowestRed ? `${lowestDate} · ${RED_DAY_WORDS}` : lowestDate}
          subTestId="calendar-lowest-date"
          bad={lowestRed}
        />
      </li>
    </ul>
  )
}
