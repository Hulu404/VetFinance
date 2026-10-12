import { useState, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useAcquiring, useConnections } from '../../api/queries'
import type { AcquiringDay, AcquiringReconciliation, Figure } from '../../api/types'
import { Banner } from '../../components/Banner'
import { FigureButton } from '../../components/FigureButton'
import { KpiCard } from '../../components/KpiCard'
import { Pill } from '../../components/Pill'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { formatDayRange, formatDayRangeLong, formatDayMonth, formatMonthTitle, monthNameLower } from '../../lib/dates'
import { formatFigure } from '../../lib/format'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { AcquiringDayDialog } from './AcquiringDayDialog'
import { settlementNote, statusView } from './acquiringText'
import { TxListSkeleton } from './TxList'

interface AcquiringCommon {
  month: string | null
  referenceYear: number | undefined
}

function useAcquiringMonth(month: string | null) {
  return useAcquiring(month ?? '', month !== null)
}

/** Three cards that replace "Доходы / Расходы / Сальдо" on the reconciliation tab. */
export function AcquiringSummary({ month }: { month: string | null }) {
  const query = useAcquiringMonth(month)
  const summary = query.data?.summary
  const hasDays = (query.data?.days.length ?? 0) > 0
  const state = query.isError && !query.data ? 'error' : query.isPending || !month ? 'loading' : 'ready'
  const monthName = month ? monthNameLower(month) : ''
  const ready = state === 'ready' && summary && hasDays

  return (
    <section aria-label={`Итоги сверки за ${monthName}`} className="tx-summary">
      <ul className="kpi-grid kpi-grid--three">
        <li>
          <KpiCard
            testId="acq-card-payments"
            label="Оплачено картой"
            emoji="💳"
            variant="detailed"
            state={ready ? 'ready' : state === 'ready' ? 'empty' : state}
            figure={summary?.card_payments}
            emptyText="оплат нет"
            extra={summary && ready ? <CommissionExtra figure={summary.commission} /> : undefined}
          />
        </li>
        <li>
          <KpiCard
            testId="acq-card-credited"
            label="Зачислено банком"
            emoji="🏦"
            variant="detailed"
            state={ready ? 'ready' : state === 'ready' ? 'empty' : state}
            figure={summary?.credited}
            emptyText="зачислений нет"
          />
        </li>
        <li>
          <KpiCard
            testId="acq-card-discrepancy"
            label="Расхождение"
            emoji="⚖️"
            variant="detailed"
            state={ready ? 'ready' : state === 'ready' ? 'empty' : state}
            figure={summary?.discrepancy}
            emptyText="расхождений нет"
            extra={summary && ready ? <WaitingExtra figure={summary.waiting} /> : undefined}
          />
        </li>
      </ul>
      {state === 'error' && (
        <button type="button" className="btn btn--text" onClick={() => void query.refetch()}>
          Повторить итоги
        </button>
      )}
    </section>
  )
}

function CommissionExtra({ figure }: { figure: Figure }) {
  return (
    <FigureButton figure={figure} title="Комиссия банка" spokenValue={`комиссия ${formatFigure(figure)}`}>
      комиссия {formatFigure(figure)}
    </FigureButton>
  )
}

function WaitingExtra({ figure }: { figure: Figure }) {
  return (
    <FigureButton figure={figure} title="Ждём зачисления" spokenValue={`ждём ещё ${formatFigure(figure)}`}>
      ждём ещё {formatFigure(figure)}
    </FigureButton>
  )
}

function Cell({ figure, title }: { figure: Figure | null; title: string }) {
  return figure ? <FigureButton figure={figure} title={title} /> : <span className="acq-dash">—</span>
}

interface RowProps {
  day: AcquiringDay
  coveredTo: string | null
  referenceYear: number | undefined
  onOpen: (day: AcquiringDay) => void
}

function DayStatus({ day, coveredTo, referenceYear }: Omit<RowProps, 'onOpen'>) {
  const view = statusView(day, coveredTo, referenceYear)
  return (
    <div className="acq-status-cell">
      <span className="acq-pills">
        <Pill variant={view.pill.variant}>{view.pill.text}</Pill>
        {day.reviewed && <Pill variant="neutral">проверено</Pill>}
      </span>
      {view.detail && <span className="acq-detail">{view.detail}</span>}
    </div>
  )
}

function rowClass(day: AcquiringDay): string {
  if (day.status === 'mismatch' && !day.reviewed) return 'acq-row acq-row--bad'
  if (day.status === 'no_payments') return 'acq-row acq-row--muted'
  return 'acq-row'
}

function OpenButton({ day, onOpen, block }: { day: AcquiringDay; onOpen: (day: AcquiringDay) => void; block: boolean }) {
  if (day.status === 'no_payments') return null
  return (
    <button
      type="button"
      className={block ? 'btn btn--block' : 'btn btn--sm'}
      aria-label={`Подробнее за ${formatDayRangeLong(day.date_from, day.date_to)}`}
      onClick={() => onOpen(day)}
    >
      Подробнее
    </button>
  )
}

function DaysTable({ days, coveredTo, referenceYear, month, onOpen }: { days: AcquiringDay[]; month: string } & Omit<RowProps, 'day'>) {
  return (
    <table className="tx-table acq-table" data-testid="acq-table">
      <caption className="sr-only">Сверка карточных оплат за {formatMonthTitle(month)}</caption>
      <thead>
        <tr>
          <th scope="col">День</th>
          <th scope="col" className="tx-th-sum">Оплаты</th>
          <th scope="col" className="tx-th-sum">Комиссия</th>
          <th scope="col" className="tx-th-sum">Ожидаем</th>
          <th scope="col" className="tx-th-sum">Зачислено</th>
          <th scope="col" className="tx-th-sum">Расхождение</th>
          <th scope="col">Статус</th>
          <th scope="col">
            <span className="sr-only">Действие</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {days.map((day) => (
          <tr key={day.date_from} className={rowClass(day)} data-testid="acq-row">
            <td className="acq-day">{formatDayRange(day.date_from, day.date_to, referenceYear)}</td>
            <td className="tx-col-sum"><Cell figure={day.card_payments} title="Оплаты картой" /></td>
            <td className="tx-col-sum"><Cell figure={day.commission} title="Комиссия" /></td>
            <td className="tx-col-sum"><Cell figure={day.expected} title="Ожидаем" /></td>
            <td className="tx-col-sum"><Cell figure={day.credited} title="Зачислено" /></td>
            <td className="tx-col-sum"><Cell figure={day.discrepancy} title="Расхождение" /></td>
            <td><DayStatus day={day} coveredTo={coveredTo} referenceYear={referenceYear} /></td>
            <td className="tx-col-act"><OpenButton day={day} onOpen={onOpen} block={false} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function DaysCards({ days, coveredTo, referenceYear, onOpen }: { days: AcquiringDay[] } & Omit<RowProps, 'day'>) {
  const pairs: [string, keyof Pick<AcquiringDay, 'card_payments' | 'commission' | 'expected' | 'credited' | 'discrepancy'>][] = [
    ['Оплаты', 'card_payments'],
    ['Комиссия', 'commission'],
    ['Ожидаем', 'expected'],
    ['Зачислено', 'credited'],
    ['Расхождение', 'discrepancy'],
  ]
  return (
    <ul className="tx-cards" data-testid="acq-cards">
      {days.map((day) => (
        <li key={day.date_from} className={`${rowClass(day)} acq-card`} data-testid="acq-row">
          <div className="acq-card__top">
            <strong>{formatDayRange(day.date_from, day.date_to, referenceYear)}</strong>
            <DayStatus day={day} coveredTo={coveredTo} referenceYear={referenceYear} />
          </div>
          <dl className="acq-card__pairs">
            {pairs.map(([label, key]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd><Cell figure={day[key]} title={label} /></dd>
              </div>
            ))}
          </dl>
          <OpenButton day={day} onOpen={onOpen} block />
        </li>
      ))}
    </ul>
  )
}

function Unavailable({ month, vetmanagerConnected, onOpenImport }: { month: string; vetmanagerConnected: boolean; onOpenImport: () => void }) {
  if (!vetmanagerConnected) {
    return (
      <EmptyState
        testId="acq-empty"
        icon="💳"
        title="Сверка пока недоступна"
        text="Для сверки нужны оплаты картой из Ветменеджера и выписка банка. Подключите Ветменеджер и загрузите выписку."
        actions={
          <>
            <Link className="btn btn--primary" to="/settings/connections/vetmanager">
              Подключить Ветменеджер
            </Link>
            <button type="button" className="btn" onClick={onOpenImport}>
              Загрузить выписку
            </button>
          </>
        }
      />
    )
  }
  return (
    <EmptyState
      testId="acq-empty"
      icon="💳"
      title={`За ${monthNameLower(month)} ${month.slice(0, 4)} оплат картой нет`}
      text="Выберите другой месяц."
    />
  )
}

function Notices({ data, onOpenImport }: { data: AcquiringReconciliation; onOpenImport: () => void }) {
  const missing = data.days.some((day) => day.status === 'no_statement')
  const anyMismatch = data.days.some((day) => day.status === 'mismatch' && !day.reviewed)
  const anyMatched = data.days.some((day) => day.status === 'matched')
  return (
    <>
      {missing && data.bank_covered_to && (
        <Banner variant="warning" testId="acq-nostatement" action={{ label: 'Загрузить выписку', onClick: onOpenImport }}>
          Выписка загружена по {formatDayMonth(data.bank_covered_to)}. Оплаты после этой даты сверить пока нельзя.
        </Banner>
      )}
      <p className="acq-note">{settlementNote(data.settlement_days)}</p>
      {!anyMismatch && anyMatched && <p className="acq-ok">Расхождений нет</p>}
    </>
  )
}

interface AcquiringPanelProps extends AcquiringCommon {
  narrow: boolean
  headingRef: RefObject<HTMLHeadingElement | null>
  onOpenImport: () => void
}

export function AcquiringPanel({ month, referenceYear, narrow, headingRef, onOpenImport }: AcquiringPanelProps) {
  const query = useAcquiringMonth(month)
  const connections = useConnections()
  const [openDay, setOpenDay] = useState<AcquiringDay | null>(null)
  const loading = query.isPending || !month
  const slow = useSlowLoading(loading)
  const data = query.data
  const vetmanager = connections.data?.items.find((item) => item.type === 'vetmanager')
  const vetmanagerConnected = vetmanager ? vetmanager.connected : true

  let body
  if (query.isError && !data) {
    body = (
      <LoadErrorCard
        testId="acq-error"
        title="Не получилось загрузить сверку"
        network={isApiError(query.error) && query.error.kind === 'network'}
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    )
  } else if (loading || !month) {
    body = <TxListSkeleton narrow={narrow} />
  } else if (!data || data.days.length === 0) {
    body = <Unavailable month={month} vetmanagerConnected={vetmanagerConnected} onOpenImport={onOpenImport} />
  } else {
    body = (
      <>
        <Notices data={data} onOpenImport={onOpenImport} />
        <div className="tx-panel">
          {narrow ? (
            <DaysCards days={data.days} coveredTo={data.bank_covered_to} referenceYear={referenceYear} onOpen={setOpenDay} />
          ) : (
            <DaysTable days={data.days} month={month} coveredTo={data.bank_covered_to} referenceYear={referenceYear} onOpen={setOpenDay} />
          )}
        </div>
      </>
    )
  }

  return (
    <div data-testid="tx-list" aria-busy={loading}>
      <h2 className="sr-only" tabIndex={-1} ref={headingRef}>
        Сверка эквайринга
      </h2>
      {loading && <p className="sr-only" role="status">Загружаем сверку</p>}
      {body}
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {openDay && (
        <AcquiringDayDialog
          day={openDay}
          coveredTo={data?.bank_covered_to ?? null}
          referenceYear={referenceYear}
          onClose={() => setOpenDay(null)}
        />
      )}
    </div>
  )
}
