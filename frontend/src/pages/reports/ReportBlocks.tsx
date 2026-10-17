import { Link } from 'react-router-dom'
import { useClinic, useDashboard } from '../../api/queries'
import type { PartialReason } from '../../api/types'
import { Banner } from '../../components/Banner'
import { formatClockTime } from '../../lib/format'
import { formatRelativeMoment, monthNameLower, monthNamePrepositional } from '../../lib/dates'
import { SKELETON_TEXT_CLASS } from './reportStyles'
import './ReportsPage.css'

export const CONNECTIONS_ROUTE = '/settings/connections/vetmanager'
export const IMPORT_ROUTE = '/transactions?import=1'
/** More partial-data strips than this are not shown; the rest go to the notes of the export file. */
const MAX_PARTIAL_BANNERS = 2

interface PartialBannerSpec {
  text: string
  action?: { label: string; to: string }
}

const CHECK_CONNECTIONS = { label: 'Проверить подключения', to: CONNECTIONS_ROUTE }
const OBLIGATIONS_LINK = { label: 'Обязательства', to: '/planning/obligations' }
const LOAD_STATEMENT = { label: 'Загрузить выписку', to: IMPORT_ROUTE }

/** Texts of design/screens/pnl.md and norm.md ("Мало данных"). The date up to which the statement reaches is not in the answer yet. */
function reportReason(report: 'pnl' | 'norm', reason: PartialReason, month: string): PartialBannerSpec | null {
  const name = monthNameLower(month)
  const prepositional = monthNamePrepositional(month)
  switch (reason) {
    case 'no_vetmanager':
      return {
        text:
          report === 'pnl'
            ? `Нет данных Ветменеджера за ${name}: выручка может быть занижена.`
            : `Нет данных Ветменеджера за ${name}: доли считаются от неполной выручки.`,
        action: CHECK_CONNECTIONS,
      }
    case 'bank_gap':
      return { text: `Выписка банка покрывает ${name} не целиком: расходы могут быть занижены.`, action: LOAD_STATEMENT }
    case 'short_period':
      return {
        text:
          report === 'pnl'
            ? `В ${prepositional} меньше недели данных: отчёт покажет картину неполно.`
            : `В ${prepositional} меньше недели данных: доли за такой срок могут сильно скакать.`,
      }
    case 'no_obligations':
      return report === 'pnl'
        ? { text: 'Не заполнены кредиты и оборудование: чистая прибыль может быть завышена.', action: OBLIGATIONS_LINK }
        : null
    case 'no_benchmark':
      return report === 'norm' ? { text: 'Для клиники вашего размера нормы пока нет: показываем доли без сравнения.' } : null
    default:
      return null
  }
}

interface StockReasonContext {
  missingExpiry: number | null | undefined
  stockUpdatedOn: string | null
}

function stockReason(reason: PartialReason, context: StockReasonContext): PartialBannerSpec | null {
  switch (reason) {
    case 'missing_expiry':
      return {
        text:
          typeof context.missingExpiry === 'number'
            ? `У ${context.missingExpiry} ${pluralBatches(context.missingExpiry)} не указан срок годности: они не попали в список сроков.`
            : 'У части партий не указан срок годности: они не попали в список сроков.',
        action: CHECK_CONNECTIONS,
      }
    case 'short_history':
      return { text: 'Расход считаем меньше чем за 90 дней: риск списания приблизительный.' }
    case 'stale_stock':
      return {
        text: context.stockUpdatedOn
          ? `Остатки склада обновлялись ${context.stockUpdatedOn}: сейчас могут отличаться.`
          : 'Остатки склада обновлялись давно: сейчас могут отличаться.',
        action: CHECK_CONNECTIONS,
      }
    default:
      return null
  }
}

function pluralBatches(count: number): string {
  const mod100 = count % 100
  const mod10 = count % 10
  if (mod100 >= 11 && mod100 <= 14) return 'партий'
  if (mod10 === 1) return 'партии'
  if (mod10 >= 2 && mod10 <= 4) return 'партий'
  return 'партий'
}

interface ReportBannersProps {
  /** Prefix of the test ids: `${prefix}-partial-banner`, `-stale-banner`, `-refresh-banner`. */
  prefix: 'pnl' | 'norm' | 'stock' | 'calendar'
  reasons: PartialReason[]
  /** Month the texts speak about (pnl and norm). */
  month: string
  stock?: StockReasonContext
  dataAsOf: string | null | undefined
  refreshFailed: boolean
  onRefresh: () => void
}

/** Strips above the report: failed refresh, partial data (up to two), stale data. */
export function ReportBanners({ prefix, reasons, month, stock, dataAsOf, refreshFailed, onRefresh }: ReportBannersProps) {
  const dashboard = useDashboard()
  const clinic = useClinic()
  const timeZone = clinic.data?.timezone
  const specs = reasons
    .map((reason) => {
      if (prefix === 'calendar') return null
      return prefix === 'stock' ? stockReason(reason, stock ?? { missingExpiry: null, stockUpdatedOn: null }) : reportReason(prefix, reason, month)
    })
    .filter((spec): spec is PartialBannerSpec => spec !== null)
    .slice(0, MAX_PARTIAL_BANNERS)
  const stale = dashboard.data?.data_stale === true
  const staleWhen = dashboard.data?.data_as_of
    ? formatRelativeMoment(dashboard.data.data_as_of, dashboard.data.as_of, timeZone)
    : null
  return (
    <>
      {refreshFailed && (
        <Banner variant="warning" testId={`${prefix}-refresh-banner`} action={{ label: 'Обновить', onClick: onRefresh }}>
          Не удалось обновить.
          {dataAsOf ? ` Показаны данные на ${formatClockTime(dataAsOf, timeZone)}.` : ''}
        </Banner>
      )}
      {specs.map((spec) => (
        <Banner key={spec.text} variant="warning" testId={`${prefix}-partial-banner`} action={spec.action}>
          {spec.text}
        </Banner>
      ))}
      {stale && (
        <Banner variant="warning" testId={`${prefix}-stale-banner`} action={CHECK_CONNECTIONS}>
          {staleWhen ? `Данные обновлены ${staleWhen} и могли устареть.` : 'Данные могли устареть.'}
        </Banner>
      )}
    </>
  )
}

/** Sentence under the header: written by the API; while loading, a placeholder of the same line. */
export function Headline({ text, loading, testId }: { text: string | null | undefined; loading: boolean; testId: string }) {
  if (loading) return <span className={`headline-skeleton ${SKELETON_TEXT_CLASS}`} aria-hidden="true" />
  if (!text) return null
  return (
    <p className="headline" data-testid={testId}>
      {text}
    </p>
  )
}

export function EmptyActions({ statementFirst }: { statementFirst: boolean }) {
  const statement = (
    <Link className="btn" to={IMPORT_ROUTE} key="statement">
      Загрузить выписку
    </Link>
  )
  const connections = (
    <Link className="btn" to={CONNECTIONS_ROUTE} key="connections">
      Подключения
    </Link>
  )
  return <>{statementFirst ? [statement, connections] : [connections, statement]}</>
}
