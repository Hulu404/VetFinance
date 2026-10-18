import { useState } from 'react'
import { Link } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useEfficiency } from '../../api/queries'
import type { EfficiencyReport } from '../../api/types'
import { Banner } from '../../components/Banner'
import { DataStrips } from '../../components/DataStrips'
import { KpiCard } from '../../components/KpiCard'
import { LoadBarSkeleton } from '../../components/LoadBar'
import { MonthSwitcher } from '../../components/MonthSwitcher'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { formatMonthTitle, monthNameLower, monthNamePrepositional, monthOf, shiftMonth } from '../../lib/dates'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { Headline, IMPORT_ROUTE, CONNECTIONS_ROUTE } from '../reports/ReportBlocks'
import { useMonthCorrection, useReportParams } from '../reports/useReportParams'
import { HourCostCard } from './HourCostCard'
import { HoursDialog } from './HoursDialog'
import { LoadList } from './LoadList'
import './EfficiencyPage.css'

const LOAD_BY_TEXT = { rooms: 'по кабинетам', doctors: 'по часам врачей' } as const
const NO_HOURS_TEXT = 'часы приёма не указаны'
const FALLBACK_NOTE = 'Расписания кабинетов нет, поэтому считаем по часам приёма врачей. Часы вы указали сами.'
const SKELETON_ROWS = 4

function Cards({ report, month }: { report: EfficiencyReport; month: string }) {
  const name = monthNameLower(month)
  return (
    <ul className="kpi-grid kpi-grid--plan" aria-label="Итоги месяца">
      <li>
        <KpiCard
          label={`Приёмов в ${monthNamePrepositional(month)}`}
          emoji="🐾"
          state="ready"
          figure={report.visits}
          figureKey="visits"
          valueTestId="efficiency-visits"
          subText="за месяц"
        />
      </li>
      <li>
        {report.load_pct ? (
          <KpiCard
            label="Загрузка"
            emoji="⏱️"
            state="ready"
            figure={report.load_pct}
            figureKey="load_pct"
            valueTestId="efficiency-load"
            subText={LOAD_BY_TEXT[report.load_by]}
          />
        ) : (
          <KpiCard label="Загрузка" emoji="⏱️" state="empty" emptyText={NO_HOURS_TEXT} dashTestId="efficiency-load" />
        )}
      </li>
      <li>
        {report.avg_check ? (
          <KpiCard
            label="Средний чек"
            emoji="🧾"
            state="ready"
            figure={report.avg_check}
            figureKey="avg_check"
            valueTestId="efficiency-avg-check"
            subText={`за ${name}`}
          />
        ) : (
          <KpiCard label="Средний чек" emoji="🧾" state="empty" emptyText="нет приёмов" dashTestId="efficiency-avg-check" />
        )}
      </li>
    </ul>
  )
}

function Banners({ report, month, onSetHours }: { report: EfficiencyReport; month: string; onSetHours: () => void }) {
  return (
    <>
      {report.partial_reasons.includes('no_doctor_hours') && (
        <Banner variant="warning" testId="efficiency-hours-banner" action={{ label: 'Указать часы приёма', onClick: onSetHours }}>
          Загрузку и стоимость часа посчитать нельзя: не указаны часы приёма врачей.
        </Banner>
      )}
      {report.partial_reasons.includes('no_expenses') && (
        <Banner variant="warning" testId="efficiency-expenses-banner" action={{ label: 'Загрузить выписку', to: IMPORT_ROUTE }}>
          Нет данных банка за {monthNameLower(month)}: стоимость часа посчитать нельзя. Загрузите выписку.
        </Banner>
      )}
    </>
  )
}

function LoadCard({ report, onSetHours }: { report: EfficiencyReport; onSetHours: () => void }) {
  const doctors = report.load_by === 'doctors'
  const noHours = report.partial_reasons.includes('no_doctor_hours')
  return (
    <section className="eff-card" aria-labelledby="eff-load-title">
      <h2 id="eff-load-title" className="eff-card__title">
        {doctors ? 'Загрузка по врачам' : 'Загрузка по кабинетам'}
      </h2>
      <LoadList report={report} onSetHours={onSetHours} />
      {doctors && (
        <div className="eff-fallback">
          <p className="eff-fallback__note" data-testid="efficiency-fallback-note">
            {noHours ? 'Расписания кабинетов нет, поэтому считаем по часам приёма врачей.' : FALLBACK_NOTE}
          </p>
          <button type="button" className={noHours ? 'btn btn--primary' : 'btn'} data-testid="efficiency-hours-open" onClick={onSetHours}>
            {noHours ? 'Указать часы приёма' : 'Изменить часы приёма'}
          </button>
        </div>
      )}
    </section>
  )
}

function Skeleton() {
  return (
    <div data-testid="efficiency-loading" aria-hidden="true">
      <ul className="kpi-grid kpi-grid--plan">
        {['🐾', '⏱️', '🧾'].map((emoji) => (
          <li key={emoji}>
            <KpiCard label="" emoji={emoji} state="loading" />
          </li>
        ))}
      </ul>
      <div className="eff-grid">
        <section className="eff-card">
          {Array.from({ length: SKELETON_ROWS }, (_, index) => (
            <LoadBarSkeleton key={index} />
          ))}
        </section>
        <section className="eff-card">
          <span className="eff-sk eff-sk--value" />
          {Array.from({ length: SKELETON_ROWS }, (_, index) => (
            <span key={index} className="eff-sk eff-sk--row" />
          ))}
        </section>
      </div>
    </div>
  )
}

export function EfficiencyPage() {
  const params = useReportParams()
  const { month, asOf, update } = params
  const query = useEfficiency(month, asOf)
  const toast = useToast()
  const [hoursOpen, setHoursOpen] = useState(false)
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)
  const fresh = data && !query.isPlaceholderData ? data : null
  useMonthCorrection(params, fresh ? fresh.month : null, error)

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const shownMonth = month ?? data?.month ?? null
  const failedWithoutData = query.isError && !data
  const lastClosed = data ? shiftMonth(monthOf(data.as_of), -1) : null
  const announce = fresh && shownMonth ? `Показан ${formatMonthTitle(shownMonth).toLowerCase()}` : ''
  const empty = data?.status === 'empty'

  return (
    <div data-testid="efficiency" data-load-by={data?.load_by} aria-busy={loading}>
      <PageHeader title="Эффективность клиники" subtitle="Загрузка, стоимость часа и средний чек" balance />
      {loading && (
        <p className="sr-only" role="status">
          Загружаем данные
        </p>
      )}
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && <DataStrips prefix="efficiency" dataAsOf={data.data_as_of} refreshFailed={query.isError && !query.isFetching} onRefresh={() => void query.refetch()} />}
      {data && shownMonth && !empty && <Banners report={data} month={shownMonth} onSetHours={() => setHoursOpen(true)} />}
      <MonthSwitcher
        month={shownMonth}
        firstMonth={fresh?.period.first_month ?? data?.period.first_month}
        currentMonth={lastClosed}
        periodStatus={fresh?.period.status}
        periodTo={fresh?.period.to}
        loading={query.isFetching}
        onChange={(next) => update({ month: next })}
        testIdPrefix="efficiency"
      />
      {loading && (
        <>
          <Headline text={null} loading testId="efficiency-headline" />
          <Skeleton />
        </>
      )}
      {failedWithoutData && (
        <LoadErrorCard
          testId="efficiency-error"
          retryTestId="efficiency-error-retry"
          title="Не получилось загрузить данные"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {data && shownMonth && empty && (
        <EmptyState
          testId="efficiency-empty"
          icon="⏱️"
          title={`За ${monthNameLower(shownMonth)} данных нет`}
          text="Загрузите продажи из Ветменеджера: экран появится, когда за месяц будут приёмы."
          actions={
            <Link className="btn" to={CONNECTIONS_ROUTE}>
              Подключения
            </Link>
          }
        />
      )}
      {data && shownMonth && !empty && (
        <div aria-busy={query.isPlaceholderData}>
          <Headline text={data.headline} loading={false} testId="efficiency-headline" />
          <Cards report={data} month={shownMonth} />
          <div className="eff-grid">
            <LoadCard report={data} onSetHours={() => setHoursOpen(true)} />
            <HourCostCard report={data} />
          </div>
        </div>
      )}
      {hoursOpen && (
        <HoursDialog
          fallbackFocus={() => document.querySelector<HTMLElement>('[data-testid="efficiency-hours-open"]')?.focus()}
          onClose={() => setHoursOpen(false)}
          onSaved={() => {
            setHoursOpen(false)
            toast.show({ message: 'Часы приёма сохранены' })
          }}
        />
      )}
    </div>
  )
}
