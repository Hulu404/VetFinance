// Date and time formatting (design/components.md, section 14). Calendar dates are plain strings
// "YYYY-MM-DD": no time zone applies to them, so they are parsed by hand and formatted without a zone.

const NBSP = ' '
const EN_DASH = '–'

const MONTHS_NOMINATIVE = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
const MONTHS_GENITIVE = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]
const MONTHS_PREPOSITIONAL = [
  'январе', 'феврале', 'марте', 'апреле', 'мае', 'июне',
  'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре',
]
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export interface CalendarDate {
  year: number
  month: number // 1..12
  day: number
}

export function parseIsoDate(iso: string): CalendarDate | null {
  const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!parts) return null
  const month = Number(parts[2])
  const day = Number(parts[3])
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  return { year: Number(parts[1]), month, day }
}

/** "2026-09-09" -> "9 сен"; the year is added when it differs from the reference year ("9 сен 2025"). */
export function formatDateShort(iso: string, referenceYear?: number): string {
  const date = parseIsoDate(iso)
  if (!date) return iso
  const base = `${date.day}${NBSP}${MONTHS_SHORT[date.month - 1]}`
  return referenceYear !== undefined && date.year !== referenceYear ? `${base}${NBSP}${date.year}` : base
}

/** "2026-09-06" -> "6 сентября". */
export function formatDayMonth(iso: string): string {
  const date = parseIsoDate(iso)
  if (!date) return iso
  return `${date.day}${NBSP}${MONTHS_GENITIVE[date.month - 1]}`
}

/** "2026-09-06" -> "6 сентября 2026". */
export function formatDateLong(iso: string): string {
  const date = parseIsoDate(iso)
  if (!date) return iso
  return `${date.day}${NBSP}${MONTHS_GENITIVE[date.month - 1]}${NBSP}${date.year}`
}

/** Year of an ISO date, to pass as the reference year of formatDateShort. */
export function yearOf(iso: string): number | undefined {
  return parseIsoDate(iso)?.year
}

/** "4–6 сен" in one month, "30 авг – 1 сен" across months. Only formats the range the API grouped. */
export function formatDayRange(from: string, to: string, referenceYear?: number): string {
  if (from === to) return formatDateShort(from, referenceYear)
  const a = parseIsoDate(from)
  const b = parseIsoDate(to)
  if (!a || !b) return `${from}${EN_DASH}${to}`
  if (a.year === b.year && a.month === b.month) {
    return `${a.day}${EN_DASH}${formatDateShort(to, referenceYear)}`
  }
  return `${formatDateShort(from, referenceYear)}${NBSP}${EN_DASH}${NBSP}${formatDateShort(to, referenceYear)}`
}

/** "4–6 сентября" (dialog titles, toasts). */
export function formatDayRangeLong(from: string, to: string): string {
  if (from === to) return formatDayMonth(from)
  const a = parseIsoDate(from)
  const b = parseIsoDate(to)
  if (!a || !b) return `${from}${EN_DASH}${to}`
  if (a.month === b.month && a.year === b.year) return `${a.day}${EN_DASH}${formatDayMonth(to)}`
  return `${formatDayMonth(from)}${NBSP}${EN_DASH}${NBSP}${formatDayMonth(to)}`
}

export function isValidMonth(value: string | null | undefined): value is string {
  if (!value) return false
  const match = /^(\d{4})-(\d{2})$/.exec(value)
  return Boolean(match) && Number(match?.[2]) >= 1 && Number(match?.[2]) <= 12
}

/** "2026-09" -> "Сентябрь 2026". */
export function formatMonthTitle(month: string): string {
  const [year, number] = month.split('-').map(Number)
  const name = MONTHS_NOMINATIVE[(number ?? 1) - 1] ?? month
  return `${name.charAt(0).toUpperCase()}${name.slice(1)}${NBSP}${year}`
}

/** "2026-09" -> "сентябрь" (for "Доходы за сентябрь"). */
export function monthNameLower(month: string): string {
  const number = Number(month.split('-')[1])
  return MONTHS_NOMINATIVE[number - 1] ?? month
}

/** "2028-11" -> "ноября 2028" (after "до" and "с": "до ноября 2028", "с октября 2026"). */
export function formatMonthGenitiveYear(month: string): string {
  const [year, number] = month.split('-').map(Number)
  return `${MONTHS_GENITIVE[(number ?? 1) - 1] ?? month}${NBSP}${year}`
}

/** "2025-09" -> "сентябрь 2025". */
export function formatMonthYear(month: string): string {
  const [year] = month.split('-').map(Number)
  return `${monthNameLower(month)}${NBSP}${year}`
}

/** "2026-09" -> "сентябре" (for "Списано в сентябре"). */
export function monthNamePrepositional(month: string): string {
  const number = Number(month.split('-')[1])
  return MONTHS_PREPOSITIONAL[number - 1] ?? month
}

/** "2026-09" -> "Сентябрь" (a heading). */
export function monthNameTitle(month: string): string {
  const name = monthNameLower(month)
  return `${name.charAt(0).toUpperCase()}${name.slice(1)}`
}

export function monthOf(isoDate: string): string {
  return isoDate.slice(0, 7)
}

/** Last calendar day of a month label: "2026-09" -> "2026-09-30". */
export function lastDayOfMonth(month: string): string {
  const [year, number] = month.split('-').map(Number)
  const day = new Date(Date.UTC(year ?? 0, number ?? 1, 0)).getUTCDate()
  return `${month}-${String(day).padStart(2, '0')}`
}

/** Calendar step over month labels ("2026-09" + 1 = "2026-10"). Not money arithmetic. */
export function shiftMonth(month: string, delta: number): string {
  const [year, number] = month.split('-').map(Number)
  const index = (year ?? 0) * 12 + ((number ?? 1) - 1) + delta
  const nextYear = Math.floor(index / 12)
  const nextMonth = (index % 12) + 1
  return `${nextYear}-${String(nextMonth).padStart(2, '0')}`
}

/** Calendar date of a timestamp in the clinic time zone, "YYYY-MM-DD". */
export function dateInZone(isoDateTime: string, timeZone?: string): string | null {
  const date = new Date(isoDateTime)
  if (Number.isNaN(date.getTime())) return null
  const options: Intl.DateTimeFormatOptions = { year: 'numeric', month: '2-digit', day: '2-digit' }
  try {
    return new Intl.DateTimeFormat('sv-SE', { ...options, timeZone }).format(date)
  } catch {
    return new Intl.DateTimeFormat('sv-SE', options).format(date)
  }
}

export function clockTime(isoDateTime: string, timeZone?: string): string {
  const date = new Date(isoDateTime)
  if (Number.isNaN(date.getTime())) return '—'
  const options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }
  try {
    return new Intl.DateTimeFormat('ru-RU', { ...options, timeZone }).format(date)
  } catch {
    return new Intl.DateTimeFormat('ru-RU', options).format(date)
  }
}

/** Calendar arithmetic on a plain date (not money): used only to name "yesterday". */
export function shiftIsoDate(iso: string, days: number): string {
  const date = parseIsoDate(iso)
  if (!date) return iso
  const shifted = new Date(Date.UTC(date.year, date.month - 1, date.day + days))
  return shifted.toISOString().slice(0, 10)
}

function dayLabel(day: string, today: string | undefined): string {
  const year = today ? yearOf(today) : undefined
  const date = parseIsoDate(day)
  return date && year !== undefined && date.year !== year ? formatDateLong(day) : formatDayMonth(day)
}

/**
 * "сегодня в 04:12", "вчера в 04:12", otherwise "8 сентября в 04:12".
 * `today` is the calendar date the API calls today (`as_of`), so the client never reads the wall clock.
 */
export function formatRelativeMoment(isoDateTime: string, today: string | undefined, timeZone?: string): string {
  const day = dateInZone(isoDateTime, timeZone)
  const time = clockTime(isoDateTime, timeZone)
  if (!day) return '—'
  if (today && day === today) return `сегодня в ${time}`
  if (today && day === shiftIsoDate(today, -1)) return `вчера в ${time}`
  return `${dayLabel(day, today)} в ${time}`
}

/** "8 сентября, 04:12" for tables; "сегодня, 04:12" for the reference day. */
export function formatRunMoment(isoDateTime: string, today: string | undefined, timeZone?: string): string {
  const day = dateInZone(isoDateTime, timeZone)
  const time = clockTime(isoDateTime, timeZone)
  if (!day) return '—'
  if (today && day === today) return `сегодня, ${time}`
  return `${dayLabel(day, today)}, ${time}`
}

/** "9 сентября, 04:12" for "Показаны данные на ...". */
export function formatMomentComma(isoDateTime: string, today: string | undefined, timeZone?: string): string {
  const day = dateInZone(isoDateTime, timeZone)
  if (!day) return '—'
  return `${dayLabel(day, today)}, ${clockTime(isoDateTime, timeZone)}`
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}${NBSP}КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')}${NBSP}МБ`
}
