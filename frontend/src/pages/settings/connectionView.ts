import type { Connection } from '../../api/types'
import type { ConnectionTone } from '../../components/ConnectionStatus'
import type { PillVariant } from '../../components/Pill'
import { formatDayMonth, formatRelativeMoment } from '../../lib/dates'

export interface ConnectionView {
  tone: ConnectionTone
  statusText: string
  pill: { text: string; variant: PillVariant } | null
}

/**
 * Status of the Vetmanager connection in words (design/components.md, section 13).
 * Which state the connection is in is the backend's decision (`last_run`, `data_stale`); the client chooses the text.
 * Priority: running, failed, partial, stale, up to date.
 */
export function vetmanagerView(connection: Connection, asOf: string | undefined, timeZone: string | undefined): ConnectionView {
  if (!connection.connected) return { tone: 'off', statusText: 'не подключено', pill: null }
  const run = connection.last_run
  if (run?.status === 'running') {
    return { tone: 'running', statusText: connection.last_success_at ? 'синхронизация идёт…' : 'загружаем историю…', pill: null }
  }
  if (run?.status === 'failed') {
    return { tone: 'failed', statusText: 'не удалось обновить', pill: { text: 'ошибка синхронизации', variant: 'danger' } }
  }
  if (run?.status === 'partial') {
    return { tone: 'partial', statusText: 'обновлено не всё', pill: { text: 'обновлено частично', variant: 'warning' } }
  }
  const updated = connection.last_success_at
    ? `обновлено ${formatRelativeMoment(connection.last_success_at, asOf, timeZone)}`
    : 'ещё не обновлялось'
  if (connection.data_stale) {
    return { tone: 'stale', statusText: updated, pill: { text: 'данные устарели', variant: 'warning' } }
  }
  return { tone: 'ok', statusText: updated, pill: null }
}

/** The latest date among bank accounts; comparing calendar dates, no arithmetic. */
export function latestStatement(connection: Connection): string | null {
  const dates = (connection.bank?.accounts ?? []).map((item) => item.last_statement_to).filter((date): date is string => Boolean(date))
  return dates.reduce<string | null>((latest, date) => (latest === null || date > latest ? date : latest), null)
}

export function bankView(connection: Connection): ConnectionView {
  const latest = latestStatement(connection)
  if (!latest) return { tone: 'off', statusText: 'выписок ещё не было', pill: null }
  const text = `последняя выписка по ${formatDayMonth(latest)}`
  if (connection.data_stale) return { tone: 'stale', statusText: text, pill: { text: 'данные устарели', variant: 'warning' } }
  return { tone: 'ok', statusText: text, pill: null }
}
