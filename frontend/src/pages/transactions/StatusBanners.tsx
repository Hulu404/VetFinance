import { useClinic, useConnections, useDashboard } from '../../api/queries'
import { Banner } from '../../components/Banner'
import { formatMomentComma, formatRelativeMoment } from '../../lib/dates'
import { syncErrorShort } from '../../lib/syncText'

const CONNECTIONS_ACTION = { label: 'Открыть подключения', to: '/settings/connections/vetmanager' }

/**
 * One strip above the month: a failed sync wins over stale data (design/screens/transactions.md, "Состояния экрана").
 * The decision "stale" or "failed" comes from the API (`data_stale`, `last_run`); the client only picks the text.
 */
export function StatusBanners() {
  const dashboard = useDashboard()
  const connections = useConnections()
  const clinic = useClinic()
  const timeZone = clinic.data?.timezone
  const asOf = dashboard.data?.as_of

  const failed = connections.data?.items.find((item) => item.last_run?.status === 'failed')
  if (failed) {
    const reason = syncErrorShort(failed.last_run?.error_code)
    const shown = failed.last_success_at
      ? `Показаны данные на ${formatMomentComma(failed.last_success_at, asOf, timeZone)}.`
      : 'Данные пока не загружались.'
    const name = failed.type === 'vetmanager' ? 'Ветменеджер' : 'Банк'
    return (
      <Banner variant="danger" testId="banner-sync-error" action={CONNECTIONS_ACTION}>
        {name} не удалось обновить: {reason}. {shown}
      </Banner>
    )
  }

  if (dashboard.data?.data_stale) {
    const when = dashboard.data.data_as_of ? formatRelativeMoment(dashboard.data.data_as_of, asOf, timeZone) : null
    return (
      <Banner variant="warning" testId="banner-stale" action={CONNECTIONS_ACTION}>
        {when ? `Данные обновлены ${when} и могли устареть.` : 'Данные могли устареть.'} Проверьте подключения.
      </Banner>
    )
  }
  return null
}
