import type { ReactNode } from 'react'
import { isApiError } from '../../api/errors'
import { useClinic, useStock } from '../../api/queries'
import type { Figure, StockExpiringRow, StockReport, StockWrittenOffRow } from '../../api/types'
import { Banner } from '../../components/Banner'
import { ExportButtons } from '../../components/ExportButtons'
import { FigureButton } from '../../components/FigureButton'
import { PageHeader } from '../../components/PageHeader'
import { Pill } from '../../components/Pill'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { dateInZone, formatDayMonth, monthNamePrepositional } from '../../lib/dates'
import { formatAsOfDate, formatCount, formatDays, formatFigure, formatMoney, pluralRu } from '../../lib/format'
import { NARROW_LIST_QUERY, useMediaQuery } from '../../lib/useMediaQuery'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { useReportParams } from './useReportParams'
import { Headline, ReportBanners } from './ReportBlocks'
import { StockIdle } from './StockIdle'
import './ReportsPage.css'

const REASON_TEXT: Record<StockWrittenOffRow['reason'], string> = {
  expired: 'истёк срок годности',
  damaged: 'порча или брак',
  other: 'другая причина',
}

function daysLeftText(days: number): string {
  return days === 0 ? 'сегодня' : formatDays(days)
}

function batchesText(count: number): string {
  return `${formatCount(count)} ${pluralRu(count, 'партия', 'партии', 'партий')}`
}

interface CardProps {
  emoji: string
  label: string
  value: Figure
  testId: string
  figureKey: string
  sub: ReactNode
}

function StockCard({ emoji, label, value, testId, figureKey, sub }: CardProps) {
  const text = formatFigure(value)
  return (
    <li>
      <div className="stock-card">
        <span className="stock-card__emoji" aria-hidden="true">
          {emoji}
        </span>
        <div className="stock-card__body">
          <span className="stock-card__label">{label}</span>
          <span className="stock-card__value" data-testid={testId} data-figure={figureKey}>
            <FigureButton figure={value} title={label} emoji={emoji} spokenValue={`${label}: ${text}`}>
              {text}
            </FigureButton>
          </span>
          {sub && <span className="stock-card__sub">{sub}</span>}
        </div>
      </div>
    </li>
  )
}

function StockCards({ report }: { report: StockReport }) {
  const month = monthNamePrepositional(report.month)
  const frozenSub =
    report.frozen.value === 0 ? (
      'всё в обороте'
    ) : (
      <span data-testid="stock-frozen-positions" data-figure="frozen_positions">
        <FigureButton figure={report.frozen_positions} title="Позиции без движения">
          {`${formatCount(report.frozen_positions.value)} ${pluralRu(report.frozen_positions.value, 'позиция', 'позиции', 'позиций')}`}
        </FigureButton>
      </span>
    )
  const atRisk = report.expiring_at_risk
  const expiringSub =
    report.expiring_60d.value === 0 ? (
      'сроки не истекают'
    ) : (
      <>
        {batchesText(report.expiring.length)}
        {atRisk && (
          <>
            {', '}
            <span data-testid="stock-expiring-risk" data-figure="expiring_at_risk">
              <FigureButton figure={atRisk} title="Может уйти в списание">
                {`может уйти в списание ${formatMoney(atRisk.value)}`}
              </FigureButton>
            </span>
          </>
        )}
      </>
    )
  const norm = report.written_off_norm
  const writtenSub = (
    <span data-testid="stock-written-off-norm" data-figure="written_off_norm">
      <FigureButton figure={norm} title="Норма списаний">
        {`норма — до ${formatMoney(norm.value)}`}
      </FigureButton>
    </span>
  )
  return (
    <ul className="stock-cards">
      <StockCard emoji="📦" label="Без движения от 60 дней" value={report.frozen} testId="stock-frozen" figureKey="frozen" sub={frozenSub} />
      <StockCard emoji="⏳" label="Срок истекает за 60 дней" value={report.expiring_60d} testId="stock-expiring" figureKey="expiring_60d" sub={expiringSub} />
      <StockCard emoji="🗑️" label={`Списано в ${month}`} value={report.written_off_month} testId="stock-written-off" figureKey="written_off_month" sub={writtenSub} />
    </ul>
  )
}

function ExpiredBanner({ report }: { report: StockReport }) {
  const figure = report.expired_on_hand
  if (figure.value <= 0) return null
  return (
    <Banner variant="warning" testId="stock-expired-banner">
      <span>
        На полке лежат партии с истёкшим сроком:{' '}
        <span data-testid="stock-expired" data-figure="expired_on_hand">
          <FigureButton figure={figure} title="Просрочено на полке" spokenValue={`Просрочено на полке: ${formatMoney(figure.value)}`}>
            {formatMoney(figure.value)}
          </FigureButton>
        </span>
        . Их стоит списать.
      </span>
    </Banner>
  )
}

function RiskCell({ row, index }: { row: StockExpiringRow; index: number }) {
  if (!row.at_risk) return <>да</>
  return (
    <span className="stock-risk">
      {`нет: может уйти в списание ${formatCount(row.at_risk.qty)} ед. на `}
      <span data-testid="stock-expiring-risk-cell" data-figure={`expiring.${index}.at_risk`}>
        <FigureButton figure={row.at_risk.amount} title={`${row.item} · риск списания`}>
          {formatMoney(row.at_risk.amount.value)}
        </FigureButton>
      </span>
    </span>
  )
}

function ExpiringRow({ row, index, withRisk, card }: { row: StockExpiringRow; index: number; withRisk: boolean; card: boolean }) {
  const amount = (
    <span data-testid="stock-expiring-amount" data-figure={`expiring.${index}.amount`}>
      <FigureButton figure={row.amount} title={row.item} spokenValue={`${row.item}: ${formatMoney(row.amount.value)}`}>
        {formatMoney(row.amount.value)}
      </FigureButton>
    </span>
  )
  const until = `до ${formatDayMonth(row.expires_on)}`
  const attrs = { 'data-testid': 'stock-expiring-row', 'data-item': row.item, 'data-days-left': row.days_left }
  if (card) {
    return (
      <li className="stock-item" {...attrs}>
        <div className="stock-item__line">
          <span className="stock-item__name" data-no-tip>
            {row.item}
          </span>
          {amount}
        </div>
        <div className="stock-item__line">
          <span className="stock-item__meta">{until}</span>
          <Pill variant="neutral">{daysLeftText(row.days_left)}</Pill>
        </div>
        {withRisk && (
          <div className="stock-item__line">
            <RiskCell row={row} index={index} />
          </div>
        )}
      </li>
    )
  }
  return (
    <tr {...attrs}>
      <th scope="row">
        <span data-no-tip>{row.item}</span>
        <span className="stock-sub">
          {until} · остаток {formatCount(row.qty)}
        </span>
      </th>
      <td>
        <Pill variant="neutral">{daysLeftText(row.days_left)}</Pill>
      </td>
      {withRisk && (
        <td>
          <RiskCell row={row} index={index} />
        </td>
      )}
      <td className="stock-num">{amount}</td>
    </tr>
  )
}

function TurnoverLine({ report }: { report: StockReport }) {
  return (
    <p className="stock-turnover">
      Оборачиваемость склада{' '}
      <span data-testid="stock-turnover" data-figure="turnover_days">
        <FigureButton figure={report.turnover_days} title="Оборачиваемость склада" emoji="⏱️">
          {formatFigure(report.turnover_days)}
        </FigureButton>
      </span>{' '}
      при норме <span data-testid="stock-norm-turnover">{formatDays(report.norm_turnover_days)}</span>.
    </p>
  )
}

function ExpiringBlock({ report }: { report: StockReport }) {
  const card = useMediaQuery(NARROW_LIST_QUERY)
  const withRisk = report.expiring.some((row) => 'at_risk' in row)
  const rows = report.expiring.map((row, index) => (
    <ExpiringRow key={`${row.item}-${row.expires_on}`} row={row} index={index} withRisk={withRisk} card={card} />
  ))
  return (
    <section className="stock-block" aria-labelledby="stock-expiring-heading">
      <h2 id="stock-expiring-heading" className="rep-caption">
        Срок годности истекает в ближайшие 60 дней
      </h2>
      {report.expiring.length === 0 ? (
        <p className="stock-calm">В ближайшие 60 дней сроки годности не истекают.</p>
      ) : card ? (
        <ul className="stock-list">{rows}</ul>
      ) : (
        <table className="stock-table">
          <caption className="sr-only">Партии, срок годности которых истекает</caption>
          <thead>
            <tr>
              <th scope="col">Позиция</th>
              <th scope="col">Осталось</th>
              {withRisk && <th scope="col">Успеем израсходовать?</th>}
              <th scope="col" className="stock-num">
                Сумма
              </th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      )}
      <TurnoverLine report={report} />
    </section>
  )
}

function dayOf(iso: string): string {
  return formatDayMonth(iso)
}

function WriteoffRow({ row, index, card }: { row: StockWrittenOffRow; index: number; card: boolean }) {
  const amount = (
    <span data-testid="stock-writeoff-amount" data-figure={`written_off_items.${index}.amount`}>
      <FigureButton figure={row.amount} title={row.item} spokenValue={`${row.item}: ${formatMoney(row.amount.value)}`}>
        {formatMoney(row.amount.value)}
      </FigureButton>
    </span>
  )
  if (card) {
    return (
      <li className="stock-item" data-testid="stock-writeoff-row">
        <div className="stock-item__line">
          <span className="stock-item__name" data-no-tip>
            {row.item}
          </span>
          {amount}
        </div>
        <div className="stock-item__line">
          <span className="stock-item__meta">
            {dayOf(row.date)} · {REASON_TEXT[row.reason]}
          </span>
        </div>
      </li>
    )
  }
  return (
    <tr data-testid="stock-writeoff-row">
      <th scope="row">
        <span data-no-tip>{row.item}</span>
      </th>
      <td>{dayOf(row.date)}</td>
      <td>{REASON_TEXT[row.reason]}</td>
      <td className="stock-num">{amount}</td>
    </tr>
  )
}

function WriteoffBlock({ report }: { report: StockReport }) {
  const card = useMediaQuery(NARROW_LIST_QUERY)
  const month = monthNamePrepositional(report.month)
  const rows = report.written_off_items.map((row, index) => <WriteoffRow key={`${row.item}-${row.date}`} row={row} index={index} card={card} />)
  return (
    <section className="stock-block" aria-labelledby="stock-writeoff-heading">
      <h2 id="stock-writeoff-heading" className="rep-caption">
        {`Что списали в ${month}`}
      </h2>
      {report.written_off_items.length === 0 ? (
        <p className="stock-calm">{`В ${month} списаний не было.`}</p>
      ) : card ? (
        <ul className="stock-list">{rows}</ul>
      ) : (
        <table className="stock-table">
          <caption className="sr-only">Списания месяца</caption>
          <thead>
            <tr>
              <th scope="col">Позиция</th>
              <th scope="col">Дата</th>
              <th scope="col">Причина</th>
              <th scope="col" className="stock-num">
                Сумма
              </th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      )}
    </section>
  )
}

function StockSkeleton() {
  const block = (rows: number, key: string) => (
    <div className="stock-block" key={key}>
      <span className="rep-skel" style={{ display: 'block', width: 240, height: 13, marginBottom: 12 }} />
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="stock-skeleton">
          <span className="rep-skel skel" />
          <span className="rep-skel skel" />
          <span className="rep-skel skel" />
        </div>
      ))}
    </div>
  )
  return (
    <div data-testid="stock-loading" aria-hidden="true">
      <ul className="stock-cards">
        {[0, 1, 2].map((index) => (
          <li key={index}>
            <div className="stock-card stock-card--loading">
              <span className="rep-skel" style={{ width: 29, height: 29 }} />
              <span className="rep-skel" style={{ width: 120, height: 22 }} />
            </div>
          </li>
        ))}
      </ul>
      {block(4, 'a')}
      {block(5, 'b')}
      {block(4, 'c')}
    </div>
  )
}

export function StockPage() {
  const { asOf } = useReportParams()
  const query = useStock(asOf)
  const clinic = useClinic()
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const failedWithoutData = query.isError && !data
  const empty = data?.status === 'empty'
  const timeZone = clinic.data?.timezone
  const stockUpdatedIso = data?.data_as_of ? dateInZone(data.data_as_of, timeZone) : null
  const subtitle = data ? `Остатки на утро ${formatAsOfDate(data.as_of)} · данные склада из Ветменеджера` : undefined

  return (
    <div data-testid="stock" aria-busy={loading}>
      <PageHeader
        title="Склад и сроки"
        subtitle={subtitle}
        subtitleLoading={loading}
        actionsFirst
        balance
        actions={<ExportButtons report="stock" asOf={asOf} disabled={loading || failedWithoutData || empty} />}
      />
      {loading && (
        <p className="sr-only" role="status">
          Загружаем склад
        </p>
      )}
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && (
        <ReportBanners
          prefix="stock"
          reasons={data.partial_reasons}
          month={data.month}
          stock={{ missingExpiry: data.missing_expiry_count, stockUpdatedOn: stockUpdatedIso ? formatDayMonth(stockUpdatedIso) : null }}
          dataAsOf={data.data_as_of}
          refreshFailed={query.isError}
          onRefresh={() => void query.refetch()}
        />
      )}
      {loading && (
        <>
          <Headline text={null} loading testId="stock-headline" />
          <StockSkeleton />
        </>
      )}
      {failedWithoutData && (
        <LoadErrorCard
          testId="stock-error"
          retryTestId="stock-error-retry"
          title="Не получилось загрузить склад"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {data && empty && (
        <EmptyState
          testId="stock-empty"
          icon="📦"
          title="Данных склада пока нет"
          text="Остатки и сроки годности появятся, когда заработает загрузка склада из Ветменеджера."
        />
      )}
      {data && !empty && (
        <>
          <Headline text={data.headline} loading={false} testId="stock-headline" />
          <StockCards report={data} />
          <ExpiredBanner report={data} />
          <ExpiringBlock report={data} />
          <StockIdle report={data} asOf={asOf} />
          <WriteoffBlock report={data} />
        </>
      )}
    </div>
  )
}
