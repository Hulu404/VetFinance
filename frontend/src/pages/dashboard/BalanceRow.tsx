import type { DashboardBalance, Figure } from '../../api/types'
import { KpiCard } from '../../components/KpiCard'
import { formatRunway } from '../../lib/format'

const RUNWAY_LABEL = 'Хватит на'
const RUNWAY_PACE = 'при текущем темпе расходов'

/** What stands under "Хватит на N дней" (design/screens/dashboard.md, "особые случаи"). */
export function runwaySubline(runway: Figure, total: Figure): string {
  if (runway.value > 0) return RUNWAY_PACE
  if (total.value < 0) return 'остаток ниже нуля'
  if (total.value === 0) return 'на счетах пусто'
  return RUNWAY_PACE
}

function RunwayCard({ runway, total }: { runway: Figure | null | undefined; total: Figure }) {
  if (!runway) {
    return (
      <KpiCard
        label={RUNWAY_LABEL}
        emoji="⏳"
        variant="accent"
        state="empty"
        emptyText="расходов пока нет"
      />
    )
  }
  return (
    <KpiCard
      testId="balance-runway"
      label={RUNWAY_LABEL}
      emoji="⏳"
      variant="accent"
      state="ready"
      figure={runway}
      figureKey="balance.runway_days"
      valueText={formatRunway(runway.value)}
      subText={runwaySubline(runway, total)}
    />
  )
}

/** "Хватит на / Касса клиники / В банке". Every number opens its own tip. */
export function BalanceRow({ balance }: { balance: DashboardBalance }) {
  return (
    <ul className="dash-row" data-testid="balance-row">
      <li>
        <RunwayCard runway={balance.runway_days} total={balance.total} />
      </li>
      {balance.cash && (
        <li>
          <KpiCard
            testId="balance-cash"
            label="Касса клиники"
            emoji="💵"
            state="ready"
            figure={balance.cash}
            figureKey="balance.cash"
            zeroText="в кассе пусто"
          />
        </li>
      )}
      <li>
        <KpiCard
          testId="balance-bank"
          label="В банке"
          emoji="💳"
          state="ready"
          figure={balance.bank}
          figureKey="balance.bank"
          zeroText="в банке пусто"
        />
      </li>
    </ul>
  )
}
