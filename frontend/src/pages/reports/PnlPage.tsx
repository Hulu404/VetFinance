import { isApiError } from '../../api/errors'
import { usePnl } from '../../api/queries'
import type { PnlReport, PnlView } from '../../api/types'
import { ExportButtons } from '../../components/ExportButtons'
import { FigureButton } from '../../components/FigureButton'
import { MonthSwitcher } from '../../components/MonthSwitcher'
import { PageHeader } from '../../components/PageHeader'
import { StatementSkeleton, StatementTable } from '../../components/ReportTable'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { StructureBar, StructureBarSkeleton } from '../../components/StructureBar'
import { Segmented } from '../../components/Tabs'
import { formatDayMonth, formatMonthTitle, monthNameLower, monthOf } from '../../lib/dates'
import { formatMoney } from '../../lib/format'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { PnlDirections } from './PnlDirections'
import { buildDirectionSegments, buildRevenueSegments, hasAnyShare, structureAriaLabel } from './pnlSegments'
import { EmptyActions, Headline, ReportBanners } from './ReportBlocks'
import { useMonthCorrection, useReportParams } from './useReportParams'
import './ReportsPage.css'

const VIEW_OPTIONS: Array<{ id: PnlView; label: string; testId: string }> = [
  { id: 'clinic', label: 'Вся клиника', testId: 'pnl-view-clinic' },
  { id: 'direction', label: 'Услуги и товары', testId: 'pnl-view-direction' },
]

const AMORTIZATION_NOTE = 'Амортизация не списывает деньги со счёта, но уменьшает прибыль.'
const DIRECTION_NOTE =
  'Закупка препаратов отнесена к товарам целиком, комиссия эквайринга общая. Распределять общие расходы и постоянные по направлениям мы пока не умеем: это будет отдельным отчётом.'

function openNote(to: string): string {
  return `Месяц ещё идёт: обязательства и амортизация взяты за весь месяц, налоги — только уплаченные на ${formatDayMonth(to)}. К концу месяца прибыль изменится.`
}

/** Loss: the bar shows the expenses and the caption says by how much they exceed the revenue (amount from the net profit row). */
function RevenueBar({ report }: { report: PnlReport }) {
  const segments = buildRevenueSegments(report.rows)
  const net = report.rows.find((row) => row.key === 'net_profit')
  if (!hasAnyShare(segments)) return null
  const loss = net !== undefined && net.amount.value < 0
  const caption =
    loss && net ? (
      <>
        Расходы больше выручки на{' '}
        <FigureButton figure={net.amount} title={net.label} tipValue={formatMoney(net.amount.value)} spokenValue={`${net.label}: ${formatMoney(net.amount.value)}`}>
          {formatMoney(Math.abs(net.amount.value))}
        </FigureButton>
        . Полоса показывает расходы, проценты — доли выручки
      </>
    ) : (
      'Куда уходит выручка'
    )
  return <StructureBar caption={caption} segments={segments} ariaLabel={structureAriaLabel('Структура выручки', segments)} />
}

function DirectionBar({ report }: { report: PnlReport }) {
  const segments = buildDirectionSegments(report.directions ?? [])
  if (!hasAnyShare(segments)) return null
  return (
    <StructureBar
      caption="Из чего состоит выручка"
      segments={segments}
      ariaLabel={structureAriaLabel('Структура выручки', segments)}
    />
  )
}

function ClinicView({ report }: { report: PnlReport }) {
  const net = report.rows.find((row) => row.key === 'net_profit')
  return (
    <>
      <RevenueBar report={report} />
      <StatementTable rows={report.rows} />
      {net && (
        <p className="footnote" data-testid="pnl-footnote">
          {net.amount.note} {AMORTIZATION_NOTE}
        </p>
      )}
    </>
  )
}

function DirectionView({ report }: { report: PnlReport }) {
  const bridge = report.rows.filter((row) => ['marginal_profit', 'fixed', 'taxes', 'obligations', 'net_profit'].includes(row.key))
  return (
    <>
      <DirectionBar report={report} />
      <PnlDirections report={report} />
      <p className="footnote" data-testid="pnl-footnote">
        {DIRECTION_NOTE}
      </p>
      <h2 className="rep-caption">От маржи до чистой прибыли</h2>
      <StatementTable rows={bridge} flat />
    </>
  )
}

function ContentSkeleton() {
  return (
    <>
      <StructureBarSkeleton />
      <StatementSkeleton />
    </>
  )
}

interface BodyProps {
  report: PnlReport
  month: string
  view: PnlView
  /** Showing the previous answer while the next one loads. */
  stale: boolean
}

function PnlBody({ report, month, view, stale }: BodyProps) {
  if (report.status === 'empty') {
    return (
      <EmptyState
        testId="pnl-empty"
        icon="📈"
        title={`За ${monthNameLower(month)} данных нет`}
        text="Загрузите выписку или подключите Ветменеджер: отчёт появится, когда за месяц будут данные."
        actions={<EmptyActions statementFirst />}
      />
    )
  }
  const open = report.period.status === 'open' && report.period.to
  const directionPending = view === 'direction' && !report.directions
  return (
    <div aria-busy={stale}>
      <Headline text={report.headline} loading={false} testId="pnl-headline" />
      {open && (
        <p className="open-note" data-testid="pnl-open-note">
          {openNote(report.period.to ?? '')}
        </p>
      )}
      {directionPending ? <ContentSkeleton /> : view === 'direction' ? <DirectionView report={report} /> : <ClinicView report={report} />}
    </div>
  )
}

export function PnlPage() {
  const params = useReportParams()
  const { month, view, asOf, update } = params
  const query = usePnl(month, view, asOf)
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)
  const fresh = data && !query.isPlaceholderData ? data : null
  useMonthCorrection(params, fresh ? fresh.month : null, error)

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const shownMonth = month ?? data?.month ?? null
  const failedWithoutData = query.isError && !data
  const empty = data?.status === 'empty'
  const exportDisabled = loading || failedWithoutData || empty
  const announce = fresh && shownMonth ? `Показан ${formatMonthTitle(shownMonth).toLowerCase()}, ${view === 'clinic' ? 'вся клиника' : 'услуги и товары'}` : ''
  const subtitle = shownMonth ? `${formatMonthTitle(shownMonth)} · наведите на сумму, чтобы увидеть, из чего она состоит` : undefined

  return (
    <div data-testid="pnl" aria-busy={loading}>
      <PageHeader
        title="Прибыль и убытки"
        subtitle={subtitle}
        subtitleLoading={loading && !subtitle}
        actionsFirst
        balance
        actions={<ExportButtons report="pnl" month={shownMonth} asOf={asOf} disabled={exportDisabled} />}
      />
      {loading && (
        <p className="sr-only" role="status">
          Загружаем отчёт
        </p>
      )}
      <p className="sr-only" aria-live="polite" data-testid="pnl-announce">
        {announce}
      </p>
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && (
        <ReportBanners
          prefix="pnl"
          reasons={data.partial_reasons}
          month={data.month}
          dataAsOf={data.data_as_of}
          refreshFailed={query.isError}
          onRefresh={() => void query.refetch()}
        />
      )}
      <MonthSwitcher
        month={shownMonth}
        firstMonth={fresh?.period.first_month ?? data?.period.first_month}
        currentMonth={data ? monthOf(data.as_of) : null}
        periodStatus={fresh?.period.status}
        periodTo={fresh?.period.to}
        loading={query.isFetching}
        onChange={(next) => update({ month: next })}
        testIdPrefix="pnl"
      />
      {!failedWithoutData && (
        <div className="rep-switch">
          <Segmented
            label="Режим отчёта"
            options={VIEW_OPTIONS}
            value={view}
            onChange={(next) => update({ view: next === 'clinic' ? null : next })}
          />
        </div>
      )}
      {loading && (
        <>
          <Headline text={null} loading testId="pnl-headline" />
          <ContentSkeleton />
        </>
      )}
      {failedWithoutData && (
        <LoadErrorCard
          testId="pnl-error"
          retryTestId="pnl-error-retry"
          title="Не получилось загрузить отчёт"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {data && shownMonth && <PnlBody report={data} month={shownMonth} view={view} stale={query.isPlaceholderData} />}
    </div>
  )
}
