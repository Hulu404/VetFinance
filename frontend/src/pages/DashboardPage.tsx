import { isApiError } from '../api/errors'
import { useClinic, useDashboard } from '../api/queries'
import type { Dashboard } from '../api/types'
import { BalanceHero } from '../components/BalanceHero'
import { Banner } from '../components/Banner'
import { PageHeader } from '../components/PageHeader'
import { LoadErrorCard } from '../components/StateBlocks'
import { formatRelativeMoment } from '../lib/dates'
import { formatAsOfDate, formatClockTime } from '../lib/format'
import { useSlowLoading } from '../lib/useSlowLoading'
import { AdviceSection } from './dashboard/AdviceSection'
import { BalanceRow } from './dashboard/BalanceRow'
import { DashboardSkeleton } from './dashboard/DashboardSkeleton'
import { DashEmpty } from './dashboard/DashEmpty'
import { MonthSection } from './dashboard/MonthSection'
import './DashboardPage.css'

const CONNECTIONS_ROUTE = '/settings/connections/vetmanager'

function headerSubtitle(data: Dashboard, timeZone: string | undefined): string {
  const date = formatAsOfDate(data.as_of)
  const freshness = data.data_as_of
    ? `данные обновлены в ${formatClockTime(data.data_as_of, timeZone)}`
    : 'данные ещё не загружались'
  return `${date} · ${freshness}`
}

interface BannersProps {
  data: Dashboard
  timeZone?: string
  refreshFailed: boolean
  onRefresh: () => void
}

function Banners({ data, timeZone, refreshFailed, onRefresh }: BannersProps) {
  const when = data.data_as_of ? formatRelativeMoment(data.data_as_of, data.as_of, timeZone) : null
  return (
    <>
      {refreshFailed && (
        <Banner variant="warning" testId="dashboard-refresh-banner" action={{ label: 'Обновить', onClick: onRefresh }}>
          Не удалось обновить.
          {data.data_as_of ? ` Показаны данные на ${formatClockTime(data.data_as_of, timeZone)}.` : ''}
        </Banner>
      )}
      {data.data_stale && (
        <Banner variant="warning" testId="dashboard-stale-banner" action={{ label: 'Проверить подключения', to: CONNECTIONS_ROUTE }}>
          {when ? `Данные обновлены ${when} и могли устареть.` : 'Данные могли устареть.'}
        </Banner>
      )}
    </>
  )
}

function Content({ data }: { data: Dashboard }) {
  const hasAccounts = data.balance.total.breakdown.length > 0
  return (
    <>
      {hasAccounts ? (
        <>
          <BalanceHero
            total={data.balance.total}
            weekChange={data.balance.week_change}
            weekChangePct={data.balance.week_change_pct}
            trend={data.balance_trend}
            trendInfo={data.balance_trend_info}
          />
          <BalanceRow balance={data.balance} />
          <p className="dash-hint">Наведите или нажмите на сумму: покажем, из чего она состоит.</p>
        </>
      ) : (
        <DashEmpty
          testId="dashboard-no-accounts"
          level={2}
          icon="💳"
          title="Счетов пока нет"
          text="Остаток появится, когда в сервисе будет хотя бы один счёт или касса."
        />
      )}
      {data.month && <MonthSection month={data.month} asOf={data.as_of} dataAsOf={data.data_as_of} />}
      <AdviceSection advice={data.advice} historyDays={data.balance_trend?.length} />
    </>
  )
}

export function DashboardPage() {
  const dashboard = useDashboard()
  const clinic = useClinic()
  const { data, error } = dashboard
  const loading = dashboard.isPending
  const slow = useSlowLoading(loading)
  const timeZone = clinic.data?.timezone

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const failedWithoutData = dashboard.isError && !data
  const subtitle = data ? <span data-testid="dashboard-subtitle">{headerSubtitle(data, timeZone)}</span> : undefined

  return (
    <div data-testid="dashboard" aria-busy={loading}>
      <PageHeader title="Рабочий стол" subtitle={subtitle} subtitleLoading={loading} />
      {loading && (
        <p className="sr-only" role="status">
          Загружаем Рабочий стол
        </p>
      )}
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && (
        <Banners
          data={data}
          timeZone={timeZone}
          refreshFailed={dashboard.isError}
          onRefresh={() => void dashboard.refetch()}
        />
      )}
      {loading && <DashboardSkeleton />}
      {failedWithoutData && (
        <LoadErrorCard
          testId="dashboard-error"
          retryTestId="dashboard-error-retry"
          title="Не получилось загрузить Рабочий стол"
          network={isApiError(error) && error.kind === 'network'}
          retrying={dashboard.isFetching}
          onRetry={() => void dashboard.refetch()}
        />
      )}
      {data && <Content data={data} />}
    </div>
  )
}
