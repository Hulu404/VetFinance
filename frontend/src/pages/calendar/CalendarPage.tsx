import { useRef, useState, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useDeletePayment } from '../../api/mutations'
import { useCalendar } from '../../api/queries'
import type { CalendarPayment, CalendarReport } from '../../api/types'
import { CalendarGrid } from '../../components/CalendarGrid'
import { CalendarList } from '../../components/CalendarList'
import { DayBreakdown } from '../../components/DayBreakdown'
import { Dialog } from '../../components/Dialog'
import { ForecastChart } from '../../components/ForecastChart'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState, InlineAlert, LoadErrorCard } from '../../components/StateBlocks'
import { Tabs, TabPanel } from '../../components/Tabs'
import { useToast } from '../../components/Toast'
import { formatDayMonth } from '../../lib/dates'
import { findDay, isRedDay, RED_DAY_WORDS, selectedDate, windowText } from '../../lib/planning'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { IMPORT_ROUTE, ReportBanners } from '../reports/ReportBlocks'
import { CalendarAlerts } from './CalendarAlerts'
import { CalendarPartial } from './CalendarPartial'
import { CalendarSkeleton } from './CalendarSkeleton'
import { CalendarSummary } from './CalendarSummary'
import { DeferralDialog, type DeferralTarget } from './DeferralDialog'
import { PaymentDialog } from './PaymentDialog'
import { SafeLine } from './SafeLine'
import { useCalendarParams, type CalendarView } from './useCalendarParams'
import './CalendarPage.css'

const VIEW_TABS: Array<{ id: CalendarView; label: string; testId: string }> = [
  { id: 'month', label: 'Календарь', testId: 'calendar-mode-month' },
  { id: 'list', label: 'Список', testId: 'calendar-mode-list' },
]
const VIEW_PREFIX = 'cal-view'
const DELETE_FAILED = 'Не получилось удалить платёж. Попробуйте ещё раз.'

type DialogState =
  | { kind: 'deferral'; target: DeferralTarget }
  | { kind: 'payment' }
  | { kind: 'delete'; payment: CalendarPayment; date: string }
  | null

function DeletePaymentDialog({ payment, date, onClose, onDeleted }: { payment: CalendarPayment; date: string; onClose: () => void; onDeleted: () => void }) {
  const remove = useDeletePayment()
  const [failed, setFailed] = useState(false)
  const busy = remove.isPending
  return (
    <Dialog
      title={`Удалить платёж «${payment.name}» на ${formatDayMonth(date)}?`}
      onClose={onClose}
      busy={busy}
      alert
      testId="calendar-payment-delete-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn--danger"
            disabled={busy}
            aria-busy={busy || undefined}
            data-testid="calendar-payment-delete-confirm"
            onClick={() => {
              setFailed(false)
              remove.mutate(payment.id, { onSuccess: onDeleted, onError: () => setFailed(true) })
            }}
          >
            {busy ? 'Удаляем…' : 'Удалить'}
          </button>
        </>
      }
    >
      {failed && <InlineAlert testId="calendar-payment-delete-error">{DELETE_FAILED}</InlineAlert>}
    </Dialog>
  )
}

interface BodyProps {
  report: CalendarReport
  view: CalendarView
  chosen: string | null
  onSelect: (date: string, byKeyboard: boolean) => void
  headingRef: RefObject<HTMLHeadingElement | null>
  onDialog: (state: DialogState) => void
}

function CalendarBody({ report, view, chosen, onSelect, headingRef, onDialog }: BodyProps) {
  const day = findDay(report, chosen)
  const dayIndex = report.days.findIndex((item) => item.date === chosen)
  const anyRed = report.days.some((item) => isRedDay(item.status))
  const gridLabel = `Платёжный календарь, ${windowText(report.window.from, report.window.to, report.as_of)}`
  return (
    <>
      <CalendarSummary summary={report.summary} />
      <CalendarAlerts alerts={report.alerts} />
      {view === 'month' ? (
        <section className="cal-card" aria-label="Календарь на 22 дня">
          <div className="cal-card__head">
            <span className="cal-card__window">{windowText(report.window.from, report.window.to, report.as_of)}</span>
            <span className="cal-legend">
              <span className="cal-legend__item"><span className="cal-legend__sq cal-legend__sq--in" aria-hidden="true" />выручка</span>
              <span className="cal-legend__item"><span className="cal-legend__sq cal-legend__sq--pay" aria-hidden="true" />платёж</span>
              <span className="cal-legend__item"><span className="cal-legend__sq cal-legend__sq--bad" aria-hidden="true" />ниже безопасного запаса</span>
            </span>
          </div>
          <p className="cal-card__phone">Календарь шире экрана: листайте вбок.</p>
          <CalendarGrid days={report.days} selectedDate={chosen} onSelect={onSelect} label={gridLabel} />
          <p className="footnote">Окно календаря — 22 дня, начиная с сегодняшнего. Нажмите на день, чтобы открыть его разбор ниже.</p>
          <SafeLine safe={report.safe_balance} safeSet={report.safe_balance_set} />
        </section>
      ) : (
        <>
          <section className="cal-card" aria-labelledby="cal-chart-caption">
            <h2 id="cal-chart-caption" className="cal-card__label">
              Как будет меняться остаток
            </h2>
            <ForecastChart
              days={report.days}
              safe={report.safe_balance}
              safeSet={report.safe_balance_set}
              anyRed={anyRed}
              lowest={report.summary.lowest}
              selectedDate={chosen}
              onSelect={(date) => onSelect(date, false)}
            />
            <SafeLine safe={report.safe_balance} safeSet={report.safe_balance_set} />
          </section>
          <section className="cal-card" aria-labelledby="cal-list-caption">
            <h2 id="cal-list-caption" className="cal-card__label">
              По дням
            </h2>
            <CalendarList days={report.days} selectedDate={chosen} onSelect={(date) => onSelect(date, false)} />
            <p className="footnote">
              Наведите на день, чтобы увидеть, из чего он складывается.
              {anyRed && ` Дни ниже безопасного запаса отмечены красным и подписью «${RED_DAY_WORDS}».`}
            </p>
          </section>
        </>
      )}
      {day && (
        <DayBreakdown
          day={day}
          index={dayIndex}
          headingRef={headingRef}
          onEditDeferral={(payment) => {
            if (!payment.counterparty) return
            onDialog({
              kind: 'deferral',
              target: { counterpartyId: payment.counterparty.id, counterpartyName: payment.counterparty.name, days: payment.max_deferral_days },
            })
          }}
          onDelete={(payment) => onDialog({ kind: 'delete', payment, date: day.date })}
        />
      )}
      <div className="cal-actions">
        <button type="button" className="btn" data-testid="calendar-add-payment" onClick={() => onDialog({ kind: 'payment' })}>
          Добавить платёж
        </button>
      </div>
    </>
  )
}

export function CalendarPage() {
  const params = useCalendarParams()
  const { view, date, asOf, setView, setDate } = params
  const query = useCalendar(asOf)
  const toast = useToast()
  const [dialog, setDialog] = useState<DialogState>(null)
  const headingRef = useRef<HTMLHeadingElement | null>(null)
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const failedWithoutData = query.isError && !data
  const empty = data?.status === 'empty'
  const chosen = data ? selectedDate(data.days, date) : null
  const subtitle = data ? (
    <span data-testid="calendar-subtitle">
      Платежи и остаток на каждый день на 22 дня вперёд · {windowText(data.window.from, data.window.to, data.as_of)}
    </span>
  ) : undefined

  const select = (next: string, byKeyboard: boolean) => {
    setDate(next)
    if (byKeyboard) globalThis.setTimeout(() => headingRef.current?.focus(), 0)
  }
  const closeDialog = () => setDialog(null)
  const saved = (message: string) => {
    closeDialog()
    toast.show({ message })
  }

  return (
    <div data-testid="calendar" aria-busy={loading || (query.isFetching && Boolean(data))}>
      <PageHeader
        title="Платёжный календарь"
        subtitle={subtitle}
        subtitleLoading={loading}
        balance
        actions={
          <Tabs prefix={VIEW_PREFIX} label="Вид календаря" tabs={VIEW_TABS} value={view} onChange={setView} disabled={empty || loading || failedWithoutData} />
        }
      />
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && (
        <ReportBanners
          prefix="calendar"
          reasons={[]}
          month={data.as_of.slice(0, 7)}
          dataAsOf={data.data_as_of}
          refreshFailed={query.isError}
          onRefresh={() => void query.refetch()}
        />
      )}
      {failedWithoutData && (
        <LoadErrorCard
          testId="calendar-error"
          retryTestId="calendar-error-retry"
          title="Не получилось загрузить календарь"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {loading && <CalendarSkeleton view={view} />}
      {data && empty && (
        <EmptyState
          testId="calendar-empty"
          icon="📅"
          title="Календарь построим по выписке банка"
          text="Загрузите выписку: найдём регулярные платежи и посчитаем остаток на каждый день."
          actions={
            <Link className="btn" to={IMPORT_ROUTE} data-testid="calendar-empty-action">
              Загрузить выписку
            </Link>
          }
        />
      )}
      {data && !empty && (
        <TabPanel prefix={VIEW_PREFIX} id={view}>
          <CalendarPartial reasons={data.partial_reasons} historyDays={data.history_days} onAddPayment={() => setDialog({ kind: 'payment' })} />
          <CalendarBody report={data} view={view} chosen={chosen} onSelect={select} headingRef={headingRef} onDialog={setDialog} />
        </TabPanel>
      )}
      {data && dialog?.kind === 'deferral' && (
        <DeferralDialog target={dialog.target} onClose={closeDialog} onSaved={() => saved('Отсрочка сохранена')} />
      )}
      {data && dialog?.kind === 'payment' && (
        <PaymentDialog
          window={data.window}
          defaultDate={chosen ?? data.window.from}
          onClose={closeDialog}
          onCreated={() => saved('Платёж добавлен')}
        />
      )}
      {dialog?.kind === 'delete' && (
        <DeletePaymentDialog payment={dialog.payment} date={dialog.date} onClose={closeDialog} onDeleted={() => saved('Платёж удалён')} />
      )}
    </div>
  )
}
