import { Pill } from './Pill'
import { formatDayMonth, formatMonthTitle, shiftMonth } from '../lib/dates'
import './MonthSwitcher.css'

interface MonthSwitcherProps {
  /** Month on the screen; null while the first answer decides it (a placeholder is shown). */
  month: string | null
  /** Earliest month with data (`period.first_month`): the previous month is not available from it. */
  firstMonth: string | null | undefined
  /** Month of `as_of`: the next month is not available from it. */
  currentMonth: string | null | undefined
  /** `period.status` and `period.to`; no pill while the period is unknown. */
  periodStatus?: 'closed' | 'open'
  periodTo?: string | null
  /** The first answer has not come yet, or the next month is loading. */
  loading: boolean
  onChange: (month: string) => void
  /** Prefix of the test ids: `${testIdPrefix}-month`, `-month-prev`, `-month-next`, `-period-status`. */
  testIdPrefix: string
}

/** "‹ Август 2026 › [месяц закрыт]" (design/components.md, section 21). */
export function MonthSwitcher({
  month,
  firstMonth,
  currentMonth,
  periodStatus,
  periodTo,
  loading,
  onChange,
  testIdPrefix,
}: MonthSwitcherProps) {
  const prevDisabled = loading || !month || (Boolean(firstMonth) && month <= (firstMonth ?? ''))
  const nextDisabled = loading || !month || !currentMonth || month >= currentMonth
  const go = (delta: number) => {
    if (month) onChange(shiftMonth(month, delta))
  }
  return (
    <div className="month-bar">
      <button
        type="button"
        className="btn month-bar__btn"
        aria-label="Предыдущий месяц"
        aria-disabled={prevDisabled}
        data-testid={`${testIdPrefix}-month-prev`}
        onClick={() => !prevDisabled && go(-1)}
      >
        <span aria-hidden="true">‹</span>
      </button>
      <h2 className="month-bar__title" data-testid={`${testIdPrefix}-month`}>
        {month ? formatMonthTitle(month) : <span className="month-bar__skeleton" aria-hidden="true" />}
      </h2>
      <button
        type="button"
        className="btn month-bar__btn"
        aria-label="Следующий месяц"
        aria-disabled={nextDisabled}
        data-testid={`${testIdPrefix}-month-next`}
        onClick={() => !nextDisabled && go(1)}
      >
        <span aria-hidden="true">›</span>
      </button>
      {periodStatus && (
        <span className="month-bar__status" data-testid={`${testIdPrefix}-period-status`}>
          {periodStatus === 'open' ? (
            <Pill variant="warning">{periodTo ? `месяц идёт, данные по ${formatDayMonth(periodTo)}` : 'месяц идёт'}</Pill>
          ) : (
            <Pill variant="neutral">месяц закрыт</Pill>
          )}
        </span>
      )}
    </div>
  )
}
