import { useTransactionSummary } from '../../api/queries'
import { KpiCard, type KpiState } from '../../components/KpiCard'
import { monthNameLower } from '../../lib/dates'

/** "Доходы / Расходы / Сальдо" of the month. The numbers and their breakdown come from the API. */
export function SummaryCards({ month }: { month: string | null }) {
  const summary = useTransactionSummary(month ?? '', month !== null)
  const state: KpiState = summary.isError && !summary.data ? 'error' : summary.data ? 'ready' : 'loading'
  const name = month ? monthNameLower(month) : ''
  return (
    <section aria-label={month ? `Итоги за ${name}` : 'Итоги'} className="tx-summary">
      <ul className="kpi-grid kpi-grid--three">
        <li>
          <KpiCard
            testId="summary-income"
            label={`Доходы за ${name}`.trim()}
            emoji="📥"
            variant="detailed"
            state={state}
            figure={summary.data?.income}
          />
        </li>
        <li>
          <KpiCard
            testId="summary-expense"
            label={`Расходы за ${name}`.trim()}
            emoji="📤"
            variant="detailed"
            state={state}
            figure={summary.data?.expense}
          />
        </li>
        <li>
          <KpiCard
            testId="summary-balance"
            label="Сальдо"
            emoji="⚖️"
            variant="detailed"
            state={state}
            figure={summary.data?.balance}
          />
        </li>
      </ul>
      {state === 'error' && (
        <button type="button" className="btn btn--text" onClick={() => void summary.refetch()}>
          Повторить итоги
        </button>
      )}
    </section>
  )
}
