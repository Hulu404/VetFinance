import { formatMonthTitle, shiftMonth } from '../../lib/dates'

interface MonthSwitchProps {
  month: string | null
  /** Month of `as_of`: the next month is not available from it. */
  currentMonth: string | null
  onChange: (month: string) => void
}

/** "‹ Сентябрь 2026 ›" (design/screens/transactions.md, "Период"). */
export function MonthSwitch({ month, currentMonth, onChange }: MonthSwitchProps) {
  const nextDisabled = !month || !currentMonth || month >= currentMonth
  return (
    <div className="month-switch" data-testid="month-switch">
      <button
        type="button"
        className="btn month-switch__btn"
        aria-label="Предыдущий месяц"
        disabled={!month}
        onClick={() => month && onChange(shiftMonth(month, -1))}
      >
        <span aria-hidden="true">‹</span>
      </button>
      <h2 className="month-switch__title" aria-live="polite">
        {month ? formatMonthTitle(month) : <span className="month-switch__skeleton" aria-hidden="true" />}
      </h2>
      <button
        type="button"
        className="btn month-switch__btn"
        aria-label="Следующий месяц"
        disabled={nextDisabled}
        onClick={() => month && onChange(shiftMonth(month, 1))}
      >
        <span aria-hidden="true">›</span>
      </button>
    </div>
  )
}
