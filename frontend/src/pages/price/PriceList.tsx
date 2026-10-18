import type { ReactNode } from 'react'
import type { ServiceItem, ServiceSort, SortOrder } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { Pill } from '../../components/Pill'
import { PILL_TEXT, rowPillKind, visitsText } from './priceView'

interface ListProps {
  items: ServiceItem[]
  selectedId: string | null
  sort: ServiceSort
  order: SortOrder
  onOpen: (id: string, opener: HTMLElement) => void
}

interface RowProps {
  item: ServiceItem
  selected: boolean
  onOpen: (id: string, opener: HTMLElement) => void
}

function Meta({ item }: { item: ServiceItem }) {
  const manual = item.source === 'manual'
  const text = [item.group, manual ? 'вручную' : null].filter(Boolean).join(' · ')
  return (
    <span className="plist__meta" data-testid="price-row-source" data-source={item.source}>
      {text}
    </span>
  )
}

function NameCell({ item, selected, onOpen }: RowProps) {
  const kind = rowPillKind(item)
  return (
    <div className="plist__what">
      <button
        type="button"
        className="plist__open"
        aria-expanded={selected}
        aria-label={`Показать разбор: ${item.name}`}
        data-testid="price-row-open"
        data-row-id={item.id}
        onClick={(event) => onOpen(item.id, event.currentTarget)}
      >
        {item.name}
      </button>
      <Meta item={item} />
      {kind && (
        <span data-testid="price-row-pill" data-kind={kind}>
          <Pill variant={kind === 'loss' ? 'danger' : kind === 'partial' ? 'warning' : 'neutral'}>{PILL_TEXT[kind]}</Pill>
        </span>
      )}
    </div>
  )
}

type RowCells = Record<'price' | 'visits' | 'margin' | 'profit', ReactNode>

function rowCells(item: ServiceItem, index: number): RowCells {
  const marginText = item.margin_pct
  const negative = marginText !== null && marginText.value < 0
  return {
    price: (
      <span data-testid="price-row-price" data-figure={`items.${index}.price`}>
        <FigureButton figure={item.price} title={`${item.name} · цена`} />
      </span>
    ),
    visits: (
      <span data-testid="price-row-visits" data-figure={`items.${index}.visits_month`}>
        <FigureButton figure={item.visits_month} title={`${item.name} · оказана`}>
          {visitsText(item.visits_month.value, item.unit_label)}
        </FigureButton>
      </span>
    ),
    margin: (
      <span data-testid="price-row-margin" data-figure={marginText ? `items.${index}.margin_pct` : undefined} className={negative ? 'plist__bad' : undefined}>
        {marginText ? <FigureButton figure={marginText} title={`${item.name} · маржа`} /> : '—'}
      </span>
    ),
    profit: (
      <span data-testid="price-row-profit" data-figure={item.monthly_profit ? `items.${index}.monthly_profit` : undefined} className={item.monthly_profit && item.monthly_profit.value < 0 ? 'plist__bad' : undefined}>
        {item.monthly_profit ? <FigureButton figure={item.monthly_profit} title={`${item.name} · прибыль за месяц`} /> : '—'}
      </span>
    ),
  }
}

function rowAttributes(item: ServiceItem, selected: boolean) {
  return {
    'data-testid': 'price-row',
    'data-id': item.id,
    'data-status': item.status,
    'data-loss': String(item.margin_pct !== null && item.margin_pct.value < 0),
    'data-selected': selected || undefined,
  }
}

export function PriceTable({ items, selectedId, sort, order, onOpen }: ListProps) {
  const ariaSort = (key: ServiceSort) => (sort === key ? (order === 'asc' ? ('ascending' as const) : ('descending' as const)) : ('none' as const))
  return (
    <div className="plist" data-testid="price-table">
      <table className="plist__table">
        <caption className="sr-only">Услуги</caption>
        <thead>
          <tr>
            <th scope="col">Услуга</th>
            <th scope="col" className="plist__num">Цена</th>
            <th scope="col" className="plist__num">Оказана</th>
            <th scope="col" className="plist__num" aria-sort={ariaSort('margin')}>
              Маржа
            </th>
            <th scope="col" className="plist__num" aria-sort={ariaSort('profit')}>
              Прибыль за месяц
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const cells = rowCells(item, index)
            const selected = item.id === selectedId
            return (
              <tr key={item.id} className="plist__row" {...rowAttributes(item, selected)}>
                <td><NameCell item={item} selected={selected} onOpen={onOpen} /></td>
                <td className="plist__num">{cells.price}</td>
                <td className="plist__num">{cells.visits}</td>
                <td className="plist__num">{cells.margin}</td>
                <td className="plist__num">{cells.profit}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function PriceCards({ items, selectedId, onOpen }: Omit<ListProps, 'sort' | 'order'>) {
  return (
    <ul className="plist__cards" data-testid="price-cards">
      {items.map((item, index) => {
        const cells = rowCells(item, index)
        const selected = item.id === selectedId
        return (
          <li key={item.id} className="plist__card" {...rowAttributes(item, selected)}>
            <NameCell item={item} selected={selected} onOpen={onOpen} />
            <dl className="plist__pairs">
              <div><dt>Цена</dt><dd>{cells.price}</dd></div>
              <div><dt>Оказана</dt><dd>{cells.visits}</dd></div>
              <div><dt>Маржа</dt><dd>{cells.margin}</dd></div>
              <div><dt>Прибыль <span className="plist__long">за месяц</span><span className="plist__short">в месяц</span></dt><dd>{cells.profit}</dd></div>
            </dl>
          </li>
        )
      })}
    </ul>
  )
}
