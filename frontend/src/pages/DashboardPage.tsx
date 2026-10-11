import { useEffect, useState } from 'react'
import { isApiError } from '../api/errors'
import { useClinic, useDashboard } from '../api/queries'
import type { Dashboard } from '../api/types'
import { KpiCard } from '../components/KpiCard'
import { PageHeader } from '../components/PageHeader'
import { Pill } from '../components/Pill'
import { formatAsOfDate, formatClockTime } from '../lib/format'
import './DashboardPage.css'

const SLOW_LOADING_MS = 8000

const NETWORK_ERROR_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите.'
const SERVER_ERROR_TEXT = 'Это сбой на нашей стороне, ваши данные не пострадали. Попробуйте ещё раз.'

function headerSubtitle(data: Dashboard, timeZone: string | undefined): string {
  const date = formatAsOfDate(data.as_of)
  const freshness = data.data_as_of
    ? `данные обновлены в ${formatClockTime(data.data_as_of, timeZone)}`
    : 'данные ещё не загружались'
  return `${date} · ${freshness}`
}

function useSlowLoading(loading: boolean): boolean {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!loading) {
      setSlow(false)
      return
    }
    const timer = window.setTimeout(() => setSlow(true), SLOW_LOADING_MS)
    return () => window.clearTimeout(timer)
  }, [loading])
  return slow
}

function LoadError({ network, retrying, onRetry }: { network: boolean; retrying: boolean; onRetry: () => void }) {
  return (
    <div className="state-card state-card--error" role="alert">
      <Pill variant="danger">не загрузилось</Pill>
      <h2 className="state-card__title">Не получилось загрузить остаток</h2>
      <p className="state-card__text">{network ? NETWORK_ERROR_TEXT : SERVER_ERROR_TEXT}</p>
      <button type="button" className="btn" onClick={onRetry} disabled={retrying}>
        {retrying ? 'Загружаем…' : 'Повторить'}
      </button>
    </div>
  )
}

function NoAccounts() {
  return (
    <div className="state-card">
      <span className="state-card__emoji" aria-hidden="true">
        💳
      </span>
      <h2 className="state-card__title">Счетов пока нет</h2>
      <p className="state-card__text">Остаток появится, когда в сервисе будет хотя бы один счёт или касса.</p>
    </div>
  )
}

function StaleBanner({ data, timeZone, onRefresh }: { data: Dashboard; timeZone?: string; onRefresh: () => void }) {
  return (
    <div className="stale-bar" role="status">
      <Pill variant="warning">не удалось обновить</Pill>
      {data.data_as_of && <span>Показаны данные на {formatClockTime(data.data_as_of, timeZone)}</span>}
      <button type="button" className="link-button" onClick={onRefresh}>
        Обновить
      </button>
    </div>
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
  const noAccounts = data !== undefined && data.balance.total.breakdown.length === 0

  let content
  if (failedWithoutData) {
    content = (
      <LoadError
        network={isApiError(error) && error.kind === 'network'}
        retrying={dashboard.isFetching}
        onRetry={() => void dashboard.refetch()}
      />
    )
  } else if (noAccounts) {
    content = <NoAccounts />
  } else {
    content = (
      <ul className="kpi-grid">
        <li>
          <KpiCard
            testId="balance-total"
            label="Остаток на счетах"
            emoji="💰"
            variant="accent"
            state={data ? 'ready' : 'loading'}
            figure={data?.balance.total}
            zeroText="на счетах пусто"
          />
        </li>
        <li>
          <KpiCard
            testId="balance-bank"
            label="В банке"
            emoji="💳"
            state={data ? 'ready' : 'loading'}
            figure={data?.balance.bank}
            zeroText="в банке пусто"
          />
        </li>
      </ul>
    )
  }

  return (
    <>
      <PageHeader
        title="Рабочий стол"
        subtitle={data ? headerSubtitle(data, timeZone) : undefined}
        subtitleLoading={loading}
      />
      <section aria-label="Остаток на счетах" aria-busy={loading}>
        {loading && <p className="sr-only" role="status">Загружаем остаток</p>}
        {dashboard.isError && data && (
          <StaleBanner data={data} timeZone={timeZone} onRefresh={() => void dashboard.refetch()} />
        )}
        {content}
        {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
        {!failedWithoutData && !noAccounts && (
          <p className="dash-hint">Наведите или нажмите на сумму: покажем, из чего она состоит.</p>
        )}
      </section>
    </>
  )
}
