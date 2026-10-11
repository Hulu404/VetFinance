import type { Figure, FigureUnit } from '../api/types'

// The client only formats. All numbers come from the API (CLAUDE.md, rule 1).

const NBSP = ' '
const MINUS = '−'

function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP)
}

/** Kopecks (integer) -> "412 800 ₽"; kopecks shown only when non-zero: "412 800,50 ₽". */
export function formatMoney(kopecks: number): string {
  const negative = kopecks < 0
  const abs = Math.abs(Math.trunc(kopecks))
  const rub = Math.floor(abs / 100)
  const kop = abs % 100
  const rubText = groupThousands(String(rub))
  const kopText = kop === 0 ? '' : `,${String(kop).padStart(2, '0')}`
  return `${negative ? MINUS : ''}${rubText}${kopText}${NBSP}₽`
}

export function formatPercent(value: number): string {
  const text = Math.abs(value).toFixed(1).replace('.', ',')
  return `${value < 0 ? MINUS : ''}${text}%`
}

export function formatCount(value: number): string {
  return `${value < 0 ? MINUS : ''}${groupThousands(String(Math.abs(Math.trunc(value))))}`
}

export function pluralDays(n: number): string {
  const abs = Math.abs(Math.trunc(n))
  const mod100 = abs % 100
  const mod10 = abs % 10
  if (mod100 >= 11 && mod100 <= 14) return 'дней'
  if (mod10 === 1) return 'день'
  if (mod10 >= 2 && mod10 <= 4) return 'дня'
  return 'дней'
}

export function formatDays(value: number): string {
  return `${formatCount(value)}${NBSP}${pluralDays(value)}`
}

export function formatByUnit(value: number | null | undefined, unit: FigureUnit): string {
  if (value === null || value === undefined) return '—'
  switch (unit) {
    case 'rub':
      return formatMoney(value)
    case 'pct':
      return formatPercent(value)
    case 'count':
      return formatCount(value)
    case 'days':
      return formatDays(value)
    default:
      return String(value)
  }
}

export function formatFigure(figure: Pick<Figure, 'value' | 'unit'>): string {
  return formatByUnit(figure.value, figure.unit)
}

const SOURCE_LABELS: Record<string, string> = {
  bank: 'Банк',
  vetmanager: 'Ветменеджер',
  manual: 'Внесено вручную',
  calc: 'Расчёт',
  bot: 'Бот',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

/** "2026-09-09" -> "9 сентября 2026". The date is a calendar date, so time zones do not apply. */
export function formatAsOfDate(isoDate: string): string {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate)
  if (!parts) return isoDate
  const date = new Date(Date.UTC(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3])))
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
    .format(date)
    .replace(/\s?г\.$/, '')
}

/** ISO timestamp -> "04:12" in the clinic time zone. */
export function formatClockTime(isoDateTime: string, timeZone?: string): string {
  const date = new Date(isoDateTime)
  if (Number.isNaN(date.getTime())) return '—'
  try {
    return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone, hourCycle: 'h23' }).format(date)
  } catch {
    return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date)
  }
}
