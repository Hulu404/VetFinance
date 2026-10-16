import { isApiError } from '../../api/errors'
import { useNorm } from '../../api/queries'
import type { NormReport } from '../../api/types'
import { Banner } from '../../components/Banner'
import { ExportButtons } from '../../components/ExportButtons'
import { MonthSwitcher } from '../../components/MonthSwitcher'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { formatMonthTitle, monthNameLower, monthOf } from '../../lib/dates'
import { NARROW_LIST_QUERY, useMediaQuery } from '../../lib/useMediaQuery'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { NormCard, NormTableRow } from './NormRows'
import { EmptyActions, Headline, ReportBanners } from './ReportBlocks'
import { useMonthCorrection, useReportParams } from './useReportParams'
import './ReportsPage.css'

const OPEN_BANNER_TEXT =
  'Месяц ещё идёт: доли считаются от неполной выручки, поэтому с нормой мы их пока не сравниваем. Сравнение появится, когда месяц закончится.'
const FOOTNOTE_TEXT =
  'Зелёная зона на шкале — норма отрасли, чёрточка — ваше значение. Наведите на число: покажем, из чего оно состоит. Доли округлены до десятых, поэтому их сумма может отличаться от 100% на 0,1.'
const NORM_SKELETON_ROWS = 9

function NormTable({ report }: { report: NormReport }) {
  return (
    <div className="norm-card">
      <table className="norm-table">
        <caption className="sr-only">Показатели клиники против нормы</caption>
        <thead>
          <tr>
            <th scope="col">Статья</th>
            <th scope="col">Норма</th>
            <th scope="col">Где вы</th>
            <th scope="col" className="norm-col-share">
              Ваша доля
            </th>
            <th scope="col">Отклонение</th>
            <th scope="col" className="norm-col-rub">
              В рублях
            </th>
          </tr>
        </thead>
        <tbody>
          {report.items.map((item) => (
            <NormTableRow key={item.key} item={item} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NormCards({ report }: { report: NormReport }) {
  return (
    <div className="norm-card">
      <ul className="norm-cards">
        {report.items.map((item) => (
          <NormCard key={item.key} item={item} />
        ))}
      </ul>
    </div>
  )
}

function NormSkeleton({ cards }: { cards: boolean }) {
  return (
    <div className="norm-card" data-testid="norm-loading" aria-hidden="true">
      {Array.from({ length: NORM_SKELETON_ROWS }, (_, index) => (
        <div key={index} className="norm-skeleton">
          <span className="rep-skel" style={{ width: '40%', height: 14 }} />
          {!cards && <span className="rep-skel" style={{ width: 80, height: 22 }} />}
          {!cards && <span className="rep-skel" style={{ width: 200, height: 24 }} />}
          <span className="rep-skel" style={{ width: 50, height: 14 }} />
          <span className="rep-skel" style={{ width: 140, height: 22 }} />
          {!cards && <span className="rep-skel" style={{ width: 70, height: 14 }} />}
        </div>
      ))}
    </div>
  )
}

interface BodyProps {
  report: NormReport
  month: string
  cards: boolean
  stale: boolean
}

function NormBody({ report, month, cards, stale }: BodyProps) {
  if (report.status === 'empty') {
    return (
      <EmptyState
        testId="norm-empty"
        icon="📊"
        title={`За ${monthNameLower(month)} доли посчитать не из чего`}
        text="Нужна выручка за месяц. Подключите Ветменеджер или загрузите выписку: норма появится, когда данные будут."
        actions={<EmptyActions statementFirst={false} />}
      />
    )
  }
  const open = report.period.status === 'open'
  return (
    <div aria-busy={stale}>
      {open && (
        <Banner variant="info" testId="norm-open-banner">
          {OPEN_BANNER_TEXT}
        </Banner>
      )}
      <Headline text={report.headline} loading={false} testId="norm-headline" />
      {cards ? <NormCards report={report} /> : <NormTable report={report} />}
      <p className="footnote" data-testid="norm-footnote">
        {FOOTNOTE_TEXT}
      </p>
    </div>
  )
}

export function NormPage() {
  const params = useReportParams()
  const { month, asOf, update } = params
  const query = useNorm(month, asOf)
  const cards = useMediaQuery(NARROW_LIST_QUERY)
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)
  const fresh = data && !query.isPlaceholderData ? data : null
  useMonthCorrection(params, fresh ? fresh.month : null, error)

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const shownMonth = month ?? data?.month ?? null
  const failedWithoutData = query.isError && !data
  const exportDisabled = loading || failedWithoutData || data?.status === 'empty'
  const announce = fresh && shownMonth ? `Показан ${formatMonthTitle(shownMonth).toLowerCase()}` : ''
  const subtitle = shownMonth ? `${formatMonthTitle(shownMonth)} · ваши показатели против нормы ветклиник на 2–6 врачей` : undefined

  return (
    <div data-testid="norm" aria-busy={loading}>
      <PageHeader
        title="Норма"
        subtitle={subtitle}
        subtitleLoading={loading && !subtitle}
        actionsFirst
        balance
        actions={<ExportButtons report="norm" month={shownMonth} asOf={asOf} disabled={exportDisabled} />}
      />
      {loading && (
        <p className="sr-only" role="status">
          Загружаем отчёт
        </p>
      )}
      <p className="sr-only" aria-live="polite" data-testid="norm-announce">
        {announce}
      </p>
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && (
        <ReportBanners
          prefix="norm"
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
        testIdPrefix="norm"
      />
      {loading && (
        <>
          <Headline text={null} loading testId="norm-headline" />
          <NormSkeleton cards={cards} />
        </>
      )}
      {failedWithoutData && (
        <LoadErrorCard
          testId="norm-error"
          retryTestId="norm-error-retry"
          title="Не получилось загрузить отчёт"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {data && shownMonth && <NormBody report={data} month={shownMonth} cards={cards} stale={query.isPlaceholderData} />}
    </div>
  )
}
