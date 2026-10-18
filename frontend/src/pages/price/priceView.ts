import type { ServiceItem, ServiceMissing } from '../../api/types'
import { formatCount, pluralRu } from '../../lib/format'

// Texts and small decisions of the price screen. Every number comes from the API; here it is only formatted.

export type RowPillKind = 'loss' | 'no_recipe' | 'partial'

/** "18 раз", "84 раза", "52 суток". The unit is the one the API sends in `unit_label`. */
export function visitsText(count: number, unitLabel: string): string {
  const unit =
    unitLabel === 'сутки' ? pluralRu(count, 'сутки', 'суток', 'суток') : unitLabel === 'раз' ? pluralRu(count, 'раз', 'раза', 'раз') : unitLabel
  return `${formatCount(count)} ${unit}`
}

export function servicesCountText(count: number): string {
  return `${formatCount(count)} ${pluralRu(count, 'услуга', 'услуги', 'услуг')}`
}

/** The plate of a row: a loss is read from the sign of the margin the API sent, the other kinds are its `status`. */
export function rowPillKind(item: Pick<ServiceItem, 'status' | 'margin_pct'>): RowPillKind | null {
  if (item.status === 'no_recipe') return 'no_recipe'
  if (item.status === 'partial') return 'partial'
  return item.margin_pct !== null && item.margin_pct.value < 0 ? 'loss' : null
}

export const PILL_TEXT: Record<RowPillKind, string> = {
  loss: 'в минус',
  no_recipe: 'нет техкарты',
  partial: 'не хватает данных',
}

export const MISSING_TEXT: Record<Exclude<ServiceMissing, 'item_no_cost'>, string> = {
  recipe: 'Нет техкарты: без неё прибыль была бы завышена, поэтому мы её не считаем.',
  hour_cost:
    'Стоимость часа пока не посчитана (нет часов приёма или данных банка): постоянные расходы не распределены, прибыль пока завышена.',
  no_expenses: 'Нет расходов за месяц: загрузите выписку. Без них прибыль услуг не считаем.',
}

export function itemNoCostText(names: string[]): string {
  if (names.length === 0) return 'У части позиций техкарты нет цены закупки на складе: они не учтены.'
  const list = names.map((name) => `«${name}»`).join(', ')
  return `У ${names.length === 1 ? 'позиции' : 'позиций'} ${list} нет цены закупки на складе: ${names.length === 1 ? 'она не учтена' : 'они не учтены'}.`
}

export type FilterId = 'all' | 'loss' | 'no_recipe'

export const FILTER_LABELS: Record<FilterId, string> = { all: 'Все', loss: 'В минус', no_recipe: 'Нет техкарты' }

export const FILTER_EMPTY_TEXT: Record<Exclude<FilterId, 'all'>, { title: string; text: string }> = {
  loss: { title: 'В минус пока ничего нет.', text: 'Таких услуг нет: ни одна не работает в минус.' },
  no_recipe: { title: 'У всех услуг есть техкарта.', text: '' },
}
