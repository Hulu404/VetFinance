import { useSearchParams } from 'react-router-dom'
import { useStockIdle } from '../../api/queries'
import type { StockIdleItem, StockIdleKey, StockReport } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { TabPanel, Tabs, type TabDef } from '../../components/Tabs'
import { formatDayMonth, parseIsoDate } from '../../lib/dates'
import { formatCount, formatMoney, pluralRu } from '../../lib/format'
import { useMediaQuery, NARROW_LIST_QUERY } from '../../lib/useMediaQuery'
import './ReportsPage.css'

/** The address says `?idle=60`; the API asks for `bucket=60_89`. */
type IdleParam = 'all' | '60' | '90' | '180'

const BUCKET_OF: Record<IdleParam, StockIdleKey> = { all: 'all', '60': '60_89', '90': '90_179', '180': '180_plus' }
const IDLE_PARAMS: IdleParam[] = ['all', '60', '90', '180']
const TAB_LABELS: Record<IdleParam, string> = {
  all: 'Все от 60 дней',
  '60': '60–89 дней',
  '90': '90–179 дней',
  '180': 'От 180 дней',
}
const IDLE_SKELETON_ROWS = 5
const PREFIX = 'stock-idle'

function isIdleParam(value: string | null): value is IdleParam {
  return value !== null && (IDLE_PARAMS as string[]).includes(value)
}

export function useIdleParam(): [IdleParam, (next: IdleParam) => void] {
  const [search, setSearch] = useSearchParams()
  const raw = search.get('idle')
  const value: IdleParam = isIdleParam(raw) ? raw : 'all'
  const set = (next: IdleParam) =>
    setSearch(
      (previous) => {
        const params = new URLSearchParams(previous)
        if (next === 'all') params.delete('idle')
        else params.set('idle', next)
        return params
      },
      { replace: true },
    )
  return [value, set]
}

function tabsOf(report: StockReport): Array<TabDef<IdleParam>> {
  return IDLE_PARAMS.map((id) => {
    const bucket = BUCKET_OF[id]
    const count = id === 'all' ? report.frozen_positions.value : (report.idle_buckets.find((item) => item.key === bucket)?.positions.value ?? 0)
    return {
      id,
      label: TAB_LABELS[id],
      count,
      ariaLabel: `${TAB_LABELS[id]}, ${formatCount(count)}`,
      testId: 'stock-idle-tab',
      data: { 'data-bucket': bucket },
    }
  })
}

function lastMovement(iso: string, referenceYear: number | undefined): string {
  const date = parseIsoDate(iso)
  const base = formatDayMonth(iso)
  return date && referenceYear !== undefined && date.year !== referenceYear ? `${base} ${date.year}` : base
}

function IdleRow({ item, index, referenceYear, card }: { item: StockIdleItem; index: number; referenceYear: number | undefined; card: boolean }) {
  const amount = (
    <span data-testid="stock-idle-amount" data-figure={`idle.items.${index}.amount`}>
      <FigureButton figure={item.amount} title={item.item} spokenValue={`${item.item}: ${formatMoney(item.amount.value)}`}>
        {formatMoney(item.amount.value)}
      </FigureButton>
    </span>
  )
  const days = `${formatCount(item.idle_days)} ${pluralRu(item.idle_days, 'день', 'дня', 'дней')} без движения`
  if (card) {
    return (
      <li className="stock-item" data-testid="stock-idle-row" data-item={item.item}>
        <div className="stock-item__line">
          <span className="stock-item__name" data-no-tip>
            {item.item}
          </span>
          {amount}
        </div>
        <div className="stock-item__line">
          <span className="stock-item__meta">
            {lastMovement(item.last_movement_on, referenceYear)} · {days}
          </span>
        </div>
      </li>
    )
  }
  return (
    <tr data-testid="stock-idle-row" data-item={item.item}>
      <th scope="row">
        <span data-no-tip>{item.item}</span>
        <span className="stock-sub">остаток {formatCount(item.qty)}</span>
      </th>
      <td>{lastMovement(item.last_movement_on, referenceYear)}</td>
      <td className="stock-num">{formatCount(item.idle_days)}</td>
      <td className="stock-num">{amount}</td>
    </tr>
  )
}

function IdleSkeleton() {
  return (
    <div aria-hidden="true" data-testid="stock-idle-loading">
      {Array.from({ length: IDLE_SKELETON_ROWS }, (_, index) => (
        <div key={index} className="stock-skeleton">
          <span className="rep-skel skel" />
          <span className="rep-skel skel" />
          <span className="rep-skel skel" />
        </div>
      ))}
    </div>
  )
}

function IdleList({ bucket, asOf, referenceYear, frozenZero }: { bucket: StockIdleKey; asOf: string | null; referenceYear: number | undefined; frozenZero: boolean }) {
  const card = useMediaQuery(NARROW_LIST_QUERY)
  const query = useStockIdle(bucket, asOf)
  if (query.isPending) return <IdleSkeleton />
  if (query.isError && !query.data) {
    return (
      <p className="stock-inline-error" role="alert" data-testid="stock-idle-error">
        Не получилось загрузить список.
        <button type="button" className="btn btn--text" onClick={() => void query.refetch()}>
          Повторить
        </button>
      </p>
    )
  }
  const items = (query.data?.pages ?? []).flatMap((page) => page.items)
  if (items.length === 0) {
    return <p className="stock-calm">{frozenZero ? 'Товаров без движения дольше 60 дней нет.' : 'В этом интервале товаров нет.'}</p>
  }
  const rows = items.map((item, index) => <IdleRow key={`${item.item}-${item.last_movement_on}`} item={item} index={index} referenceYear={referenceYear} card={card} />)
  return (
    <div aria-busy={query.isFetching && !query.isFetchingNextPage}>
      {card ? (
        <ul className="stock-list">{rows}</ul>
      ) : (
        <table className="stock-table">
          <caption className="sr-only">Товары без движения</caption>
          <thead>
            <tr>
              <th scope="col">Позиция</th>
              <th scope="col">Последнее движение</th>
              <th scope="col" className="stock-num">
                Дней без движения
              </th>
              <th scope="col" className="stock-num">
                Сумма
              </th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      )}
      <div className="stock-more">
        {query.hasNextPage && (
          <button type="button" className="btn" data-testid="stock-idle-more" aria-busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {query.isFetchingNextPage ? 'Загружаем…' : 'Показать ещё'}
          </button>
        )}
        <span className="stock-more__note">
          Показаны {formatCount(items.length)} {pluralRu(items.length, 'позиция', 'позиции', 'позиций')} с наибольшей суммой. Полный список — в файле Excel.
        </span>
      </div>
      {query.isError && query.data && (
        <p className="stock-inline-error" role="alert">
          Не получилось загрузить список.
          <button type="button" className="btn btn--text" onClick={() => void query.fetchNextPage()}>
            Повторить
          </button>
        </p>
      )}
    </div>
  )
}

/** "Товары без движения": four intervals as tabs, the interval is kept in the address. */
export function StockIdle({ report, asOf }: { report: StockReport; asOf: string | null }) {
  const [idle, setIdle] = useIdleParam()
  const referenceYear = parseIsoDate(report.as_of)?.year
  return (
    <section className="stock-block" aria-labelledby="stock-idle-heading">
      <h2 id="stock-idle-heading" className="rep-caption">
        Товары без движения
      </h2>
      <Tabs prefix={PREFIX} label="Интервал без движения" tabs={tabsOf(report)} value={idle} onChange={setIdle} />
      <TabPanel prefix={PREFIX} id={idle}>
        <IdleList bucket={BUCKET_OF[idle]} asOf={asOf} referenceYear={referenceYear} frozenZero={report.frozen.value === 0} />
      </TabPanel>
    </section>
  )
}
