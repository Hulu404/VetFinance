import type { CalendarDay, CalendarReport, DayStatus, PaymentSource } from '../api/types'
import { formatDayMonth, parseIsoDate, shiftIsoDate, yearOf } from './dates'
import { formatMoney, pluralRu } from './format'

// Display helpers of the payment calendar. Layout by weeks and words for dates only: no money arithmetic here.

const NBSP = ' '
const EN_DASH = '–'

const WEEKDAY_FULL: Record<string, string> = {
  пн: 'понедельник',
  вт: 'вторник',
  ср: 'среда',
  чт: 'четверг',
  пт: 'пятница',
  сб: 'суббота',
  вс: 'воскресенье',
}
export const WEEKDAY_HEADERS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'] as const
const WEEKDAY_ORDER = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
const WEEK_LENGTH = 7

/** "below_safe" and "below_zero" are both a red day, with the same words. */
export function isRedDay(status: DayStatus): boolean {
  return status !== 'ok'
}

export const RED_DAY_WORDS = 'ниже запаса'

export function weekdayFull(weekday: string): string {
  return WEEKDAY_FULL[weekday] ?? weekday
}

/** "11 сентября, пятница". */
export function dayTitle(day: Pick<CalendarDay, 'date' | 'weekday'>): string {
  return `${formatDayMonth(day.date)}, ${weekdayFull(day.weekday)}`
}

/** "ещё 1 платёж", "ещё 2 платежа", "ещё 5 платежей": a count of rows, no sum (rule 1). */
export function moreLabel(count: number): string {
  return `ещё ${count}${NBSP}${pluralRu(count, 'платёж', 'платежа', 'платежей')}`
}

export function paymentsCountText(count: number): string {
  return `${count}${NBSP}${pluralRu(count, 'платёж', 'платежа', 'платежей')}`
}

/** "отсрочка 5 дней", "отсрочка 1 день", "без отсрочки". */
export function deferralLabel(days: number): string {
  if (days <= 0) return 'без отсрочки'
  return `отсрочка ${days}${NBSP}${pluralRu(days, 'день', 'дня', 'дней')}`
}

const SOURCE_WORD: Record<PaymentSource, string> = {
  recurring: 'регулярный',
  obligation: 'обязательство',
  manual: 'внесён вручную',
}

export function paymentSourceWord(source: PaymentSource): string {
  return SOURCE_WORD[source]
}

/** "9 сентября – 30 сентября"; the year is added when it differs from the year of the reference date. */
export function windowText(from: string, to: string, referenceDate: string): string {
  const year = yearOf(referenceDate)
  const part = (iso: string) => {
    const text = formatDayMonth(iso)
    const y = yearOf(iso)
    return y !== undefined && year !== undefined && y !== year ? `${text}${NBSP}${y}` : text
  }
  return `${part(from)}${NBSP}${EN_DASH}${NBSP}${part(to)}`
}

/** The day the breakdown shows first: the address date if it is in the window, else the first red day, else the first day. */
export function selectedDate(days: CalendarDay[], requested: string | null): string | null {
  if (days.length === 0) return null
  if (requested && days.some((day) => day.date === requested)) return requested
  return (days.find((day) => isRedDay(day.status)) ?? days[0])?.date ?? null
}

export type GridCell =
  | { kind: 'past'; date: string; dayNumber: number }
  | { kind: 'out'; date: string; dayNumber: number }
  | { kind: 'day'; date: string; dayNumber: number; day: CalendarDay; today: boolean; monthStart: boolean }

/**
 * Monday to Sunday weeks that cover the window: days before the first one are "прошёл", days after the last one are "вне окна".
 * This is a layout of the days the API gave, not a calculation.
 */
export function buildGrid(days: CalendarDay[]): GridCell[][] {
  const first = days[0]
  const last = days[days.length - 1]
  if (!first || !last) return []
  const lead = Math.max(0, WEEKDAY_ORDER.indexOf(first.weekday))
  const trail = WEEK_LENGTH - 1 - Math.max(0, WEEKDAY_ORDER.indexOf(last.weekday))
  const cells: GridCell[] = []
  for (let i = lead; i > 0; i -= 1) {
    const date = shiftIsoDate(first.date, -i)
    cells.push({ kind: 'past', date, dayNumber: parseIsoDate(date)?.day ?? 0 })
  }
  for (const day of days) {
    const dayNumber = parseIsoDate(day.date)?.day ?? 0
    cells.push({ kind: 'day', date: day.date, dayNumber, day, today: day.date === first.date, monthStart: dayNumber === 1 })
  }
  for (let i = 1; i <= trail; i += 1) {
    const date = shiftIsoDate(last.date, i)
    cells.push({ kind: 'out', date, dayNumber: parseIsoDate(date)?.day ?? 0 })
  }
  const weeks: GridCell[][] = []
  for (let i = 0; i < cells.length; i += WEEK_LENGTH) weeks.push(cells.slice(i, i + WEEK_LENGTH))
  return weeks
}

/** Looks the day up by date; the grid and the list share one source. */
export function findDay(report: Pick<CalendarReport, 'days'>, date: string | null): CalendarDay | null {
  return report.days.find((day) => day.date === date) ?? null
}

const SHORT_MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

/** "1 окт" for the first day of a month in the grid. */
export function monthStartLabel(iso: string): string {
  const date = parseIsoDate(iso)
  return date ? `${date.day}${NBSP}${SHORT_MONTHS[date.month - 1]}` : iso
}

/** 0 for "пн" … 6 for "вс": the column of a day in the Monday-first grid. */
export function weekdayIndex(weekday: string): number {
  return Math.max(0, WEEKDAY_ORDER.indexOf(weekday))
}

/** "− 258 000 ₽": an outgoing payment shown with the minus sign and a space (the API keeps payments positive). */
export function formatOutgoing(kopecks: number): string {
  return `−${NBSP}${formatMoney(Math.abs(kopecks))}`
}

/** "+ 46 000 ₽": the forecast income of a day. */
export function formatIncoming(kopecks: number): string {
  return `+${NBSP}${formatMoney(Math.abs(kopecks))}`
}

/** The word before the number of "balance after" a payment: enough money left, or how much is missing. */
export function afterWord(balanceAfter: number): string {
  return balanceAfter < 0 ? 'не хватит' : 'останется'
}

/** 12 -> "12%", 12.5 -> "12,5%": the rate is an input of the owner, shown as typed (up to two decimals). */
export function formatRate(rate: number): string {
  const text = Number.isInteger(rate) ? String(rate) : String(Number(rate.toFixed(2))).replace('.', ',')
  return `${text}%`
}

/** "7 лет", "1 год", "3 года". */
export function yearsText(years: number): string {
  return `${years}${NBSP}${pluralRu(years, 'год', 'года', 'лет')}`
}

/** "2 обязательства". */
export function obligationsCountText(count: number): string {
  return `${count}${NBSP}${pluralRu(count, 'обязательство', 'обязательства', 'обязательств')}`
}
