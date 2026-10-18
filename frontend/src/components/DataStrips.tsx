import { useClinic, useDashboard } from '../api/queries'
import { formatRelativeMoment } from '../lib/dates'
import { formatClockTime } from '../lib/format'
import { Banner } from './Banner'

const CHECK_CONNECTIONS = { label: 'Проверить подключения', to: '/settings/connections/vetmanager' }

interface DataStripsProps {
  /** Prefix of the test ids: `${prefix}-stale-banner`, `${prefix}-refresh-banner`. */
  prefix: string
  dataAsOf: string | null | undefined
  refreshFailed: boolean
  onRefresh: () => void
}

/** Strips above a screen: a failed refresh (numbers stay) and stale data (`data_stale` of the dashboard). */
export function DataStrips({ prefix, dataAsOf, refreshFailed, onRefresh }: DataStripsProps) {
  const dashboard = useDashboard()
  const clinic = useClinic()
  const timeZone = clinic.data?.timezone
  const stale = dashboard.data?.data_stale === true
  const staleWhen = dashboard.data?.data_as_of ? formatRelativeMoment(dashboard.data.data_as_of, dashboard.data.as_of, timeZone) : null
  return (
    <>
      {refreshFailed && (
        <Banner variant="warning" testId={`${prefix}-refresh-banner`} action={{ label: 'Обновить', onClick: onRefresh }}>
          Не удалось обновить.
          {dataAsOf ? ` Показаны данные на ${formatClockTime(dataAsOf, timeZone)}.` : ''}
        </Banner>
      )}
      {stale && (
        <Banner variant="warning" testId={`${prefix}-stale-banner`} action={CHECK_CONNECTIONS}>
          {staleWhen ? `Данные обновлены ${staleWhen} и могли устареть.` : 'Данные могли устареть.'}
        </Banner>
      )}
    </>
  )
}
