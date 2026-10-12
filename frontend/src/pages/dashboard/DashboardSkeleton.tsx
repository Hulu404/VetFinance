import { BalanceHeroSkeleton } from '../../components/BalanceHero'
import { KpiCard } from '../../components/KpiCard'

function AdviceSkeleton() {
  return (
    <li className="advice-skeleton" aria-hidden="true">
      <span className="advice-skeleton__title" />
      <span className="advice-skeleton__line" />
    </li>
  )
}

/** First load, no data yet: the shape of the screen in grey (design/screens/dashboard.md, "Загрузка"). */
export function DashboardSkeleton() {
  return (
    <div data-testid="dashboard-loading">
      <BalanceHeroSkeleton />
      <ul className="dash-row" aria-hidden="true">
        <li>
          <KpiCard label="" emoji="⏳" variant="accent" state="loading" />
        </li>
        <li>
          <KpiCard label="" emoji="💵" state="loading" />
        </li>
        <li>
          <KpiCard label="" emoji="💳" state="loading" />
        </li>
      </ul>
      <ul className="dash-row dash-row--month" aria-hidden="true">
        <li>
          <KpiCard label="" emoji="📈" variant="detailed" state="loading" />
        </li>
        <li>
          <KpiCard label="" emoji="📉" variant="detailed" state="loading" />
        </li>
        <li>
          <KpiCard label="" emoji="💰" variant="detailed" state="loading" />
        </li>
      </ul>
      <ul className="advice-list" aria-hidden="true">
        <AdviceSkeleton />
        <AdviceSkeleton />
      </ul>
    </div>
  )
}
