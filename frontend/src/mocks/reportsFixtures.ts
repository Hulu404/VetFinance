// Mock data of the three reports. The base is the example of the contract (golden set 4, `backend/openapi.json`).
// The states the example does not have (open month, loss, partial data, empty) are small variants written by hand in the same
// shape. Numbers are literals: the mock is a fake backend, the client never computes (CLAUDE.md, rule 1).
import type {
  Figure,
  NormItem,
  NormReport,
  PartialReason,
  PnlReport,
  PnlRow,
  StockIdlePage,
  StockReport,
} from '../api/types'
import { formatDayMonth, monthNamePrepositional, monthNameLower } from '../lib/dates'
import examples from './data/reports_set04.json'

interface ReportExamples {
  pnl_clinic: PnlReport
  pnl_direction: PnlReport
  norm: NormReport
  stock: StockReport
  stock_idle: StockIdlePage
}

const base = examples as unknown as ReportExamples

export const pnlClinicExample: PnlReport = base.pnl_clinic
export const pnlDirectionExample: PnlReport = base.pnl_direction
export const normExample: NormReport = base.norm
export const stockExample: StockReport = base.stock
export const stockIdleExample: StockIdlePage = base.stock_idle

/** First month with data in the example; earlier months are empty. */
export const FIRST_MONTH = '2026-07'
/** Reference date of the example answers (the month 2026-09 is closed on it). */
export const DEFAULT_AS_OF = '2026-10-01'
/** Reference date of the scenario "open month" (design/screens/pnl.md: "данные по 9 сентября"). */
export const OPEN_AS_OF = '2026-09-09'

const rubFig = (value: number, label: string, note: string, source: Figure['source'] = ['calc']): Figure => ({
  value,
  unit: 'rub',
  breakdown: [{ label, value, unit: 'rub' }],
  source,
  note,
})

const pctFig = (value: number, rubValue: number, label: string): Figure => ({
  value,
  unit: 'pct',
  breakdown: [
    { label: 'Сумма строки', value: rubValue, unit: 'rub' },
    { label: 'Выручка', value: 52000000, unit: 'rub' },
  ],
  source: ['calc'],
  note: `${label}: доля выручки.`,
})

function rowOf(key: string, label: string, kind: PnlRow['kind'], amount: number, share: number | null, note: string, children?: PnlRow[]): PnlRow {
  return {
    key,
    label,
    kind,
    amount: rubFig(amount, label, note, ['bank', 'vetmanager']),
    ...(share === null ? {} : { share_pct: pctFig(share, amount, label) }),
    ...(children ? { children } : {}),
  }
}

/** Open month, numbers of design/screens/pnl.md ("Месяц идёт"): 520 000 − 190 000 − 205 000 − 0 − 33 400 = 91 600 (all in kopecks). */
function openRows(asOf: string): PnlRow[] {
  const until = formatDayMonth(asOf)
  const monthName = monthNameLower(monthOfDate(asOf))
  return [
    rowOf('revenue', 'Выручка', 'revenue', 52000000, 100, `Закрытые счета Ветменеджера по ${until}.`),
    rowOf('variable', 'Переменные расходы', 'expense', 19000000, 36.5, `Расходы по деньгам по ${until}.`),
    rowOf('marginal_profit', 'Маржинальная прибыль', 'subtotal', 33000000, 63.5, 'Выручка минус переменные расходы.'),
    rowOf('fixed', 'Постоянные расходы', 'expense', 20500000, 39.4, `Расходы по деньгам по ${until}.`, [
      rowOf('fixed_payroll', 'ФОТ (оклады)', 'child', 6000000, 11.5, 'Оклады за период.'),
      rowOf('fixed_other', 'Аренда и прочие постоянные', 'child', 14500000, 27.9, 'Аренда, расходные материалы, прочее.'),
    ]),
    rowOf('taxes', 'Налоги и взносы', 'expense', 0, 0, `Только то, что уже уплачено на ${until}. Налоги за месяц платятся позже, поэтому сейчас прибыль выше, чем будет к концу месяца.`),
    rowOf('obligations', 'Обязательства и амортизация', 'expense', 3340000, 6.4, `Начислено за весь ${monthName}, а не за часть месяца: проценты, платёж по лизингу и амортизация по месяцу целиком.`),
    rowOf('net_profit', 'Чистая прибыль', 'total', 9160000, 17.6, 'Выручка 520 000 ₽ − переменные 190 000 ₽ − постоянные 205 000 ₽ − налоги и взносы 0 ₽ − обязательства и амортизация 33 400 ₽ = 91 600 ₽.'),
  ]
}

/** Loss of 40 000 ₽: 600 000 − 300 000 − 250 000 − 40 000 − 50 000 = −40 000 (kopecks). */
function lossRows(): PnlRow[] {
  const share = (value: number, rubValue: number, label: string): Figure => ({ ...pctFig(value, rubValue, label), breakdown: [
    { label: 'Сумма строки', value: rubValue, unit: 'rub' },
    { label: 'Выручка', value: 60000000, unit: 'rub' },
  ] })
  const withShare = (row: PnlRow, value: number): PnlRow => ({ ...row, share_pct: share(value, row.amount.value, row.label) })
  return [
    withShare(rowOf('revenue', 'Выручка', 'revenue', 60000000, null, 'Закрытые счета Ветменеджера.'), 100),
    withShare(rowOf('variable', 'Переменные расходы', 'expense', 30000000, null, 'Расходы по деньгам.'), 50),
    withShare(rowOf('marginal_profit', 'Маржинальная прибыль', 'subtotal', 30000000, null, 'Выручка минус переменные расходы.'), 50),
    {
      ...withShare(rowOf('fixed', 'Постоянные расходы', 'expense', 25000000, null, 'Расходы по деньгам.'), 41.7),
      children: [
        withShare(rowOf('fixed_payroll', 'ФОТ (оклады)', 'child', 9000000, null, 'Оклады.'), 15),
        withShare(rowOf('fixed_other', 'Аренда и прочие постоянные', 'child', 16000000, null, 'Аренда и прочее.'), 26.7),
      ],
    },
    withShare(rowOf('taxes', 'Налоги и взносы', 'expense', 4000000, null, 'Налоги и взносы за месяц.'), 6.7),
    withShare(rowOf('obligations', 'Обязательства и амортизация', 'expense', 5000000, null, 'Проценты и амортизация.'), 8.3),
    withShare(rowOf('net_profit', 'Чистый убыток', 'total', -4000000, null, 'Выручка 600 000 ₽ − переменные 300 000 ₽ − постоянные 250 000 ₽ − налоги и взносы 40 000 ₽ − обязательства и амортизация 50 000 ₽ = −40 000 ₽.'), -6.7),
  ]
}

export function monthOfDate(isoDate: string): string {
  return isoDate.slice(0, 7)
}

function lastDay(month: string): string {
  const [year, number] = month.split('-').map(Number)
  const day = new Date(Date.UTC(year ?? 0, number ?? 1, 0)).getUTCDate()
  return `${month}-${String(day).padStart(2, '0')}`
}

function previousMonth(month: string): string {
  const [year, number] = month.split('-').map(Number)
  const index = (year ?? 0) * 12 + ((number ?? 1) - 1) - 1
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

/** The last month that ended by `asOf` (the month of `asOf` itself when it is its last day). */
export function lastClosedMonth(asOf: string): string {
  const month = monthOfDate(asOf)
  return asOf >= lastDay(month) ? month : previousMonth(month)
}

export interface ReportPeriodInput {
  month: string
  asOf: string
}

function periodOf({ month, asOf }: ReportPeriodInput): PnlReport['period'] {
  const open = asOf < lastDay(month)
  return { month, status: open ? 'open' : 'closed', from: `${month}-01`, to: open ? asOf : null, first_month: FIRST_MONTH }
}

const NO_HEADLINE = { headline: undefined }

export interface PnlOptions extends ReportPeriodInput {
  view: 'clinic' | 'direction'
  scenario: string
}

export function buildPnl({ month, asOf, view, scenario }: PnlOptions): PnlReport {
  const source = view === 'direction' ? pnlDirectionExample : pnlClinicExample
  const period = periodOf({ month, asOf })
  const empty = scenario === 'reportempty' || month < FIRST_MONTH
  const common = { ...source, month, as_of: asOf, period }
  if (empty) {
    const zero = (row: PnlRow): PnlRow => ({
      ...row,
      amount: { ...row.amount, value: 0, breakdown: [] },
      share_pct: undefined,
      children: row.children?.map(zero),
    })
    return { ...common, status: 'empty', partial_reasons: [], rows: source.rows.map(zero), ...NO_HEADLINE, directions: undefined, common_variable: undefined, data_as_of: null }
  }
  if (period.status === 'open') {
    return {
      ...common,
      data_as_of: `${asOf}T04:12:00+03:00`,
      headline: `К ${formatDayMonth(asOf)} клиника заработала 91 600 ₽ чистыми: 17,6% выручки.`,
      rows: openRows(asOf),
      directions: view === 'direction' ? source.directions : undefined,
    }
  }
  if (scenario === 'reportloss') {
    return { ...common, headline: `В ${monthNamePrepositional(month)} расходы были больше выручки на 40 000 ₽.`, rows: lossRows() }
  }
  if (scenario === 'reportzero') {
    const noShare = (row: PnlRow): PnlRow => ({ ...row, share_pct: undefined, children: row.children?.map(noShare) })
    return { ...common, headline: `В ${monthNamePrepositional(month)} выручки нет, расходы 632 000 ₽.`, rows: source.rows.map(noShare) }
  }
  if (scenario === 'reportpartial') {
    const reasons: PartialReason[] = ['no_vetmanager', 'bank_gap', 'short_period', 'no_obligations']
    return { ...common, status: 'partial', partial_reasons: reasons }
  }
  return common
}

/** Open month of "Норма": no statuses, tones and deviations, the norms stay (design/screens/norm.md). */
function withoutVerdicts(item: NormItem): NormItem {
  const { status, tone, deviation_pp, deviation_rub, ...rest } = item
  void status
  void tone
  void deviation_pp
  void deviation_rub
  return rest
}

function withoutNorm(item: NormItem): NormItem {
  const { norm, deviation_pp, deviation_rub, ...rest } = withoutVerdicts(item)
  void norm
  void deviation_pp
  void deviation_rub
  return { ...rest, status: 'no_norm', tone: 'neutral' }
}

export function buildNorm({ month, asOf, scenario }: ReportPeriodInput & { scenario: string }): NormReport {
  const period = periodOf({ month, asOf })
  const common = { ...normExample, month, as_of: asOf, period }
  if (scenario === 'reportempty' || month < FIRST_MONTH) {
    return { ...common, status: 'empty', partial_reasons: [], items: [], headline: undefined, data_as_of: null }
  }
  if (period.status === 'open') {
    return {
      ...common,
      data_as_of: `${asOf}T04:12:00+03:00`,
      headline: `К ${formatDayMonth(asOf)} доли статей посчитаны от выручки за ${Number(asOf.slice(8))} дней. Сравним с нормой, когда месяц закончится.`,
      items: normExample.items.map(withoutVerdicts),
    }
  }
  if (scenario === 'reportpartial') {
    return {
      ...common,
      status: 'partial',
      partial_reasons: ['no_vetmanager', 'bank_gap', 'short_period', 'no_benchmark'],
      headline: 'Нормы для вашей клиники пока нет, но доли статей ниже.',
      items: normExample.items.map(withoutNorm),
    }
  }
  return common
}

function zeroFigure(unit: Figure['unit']): Figure {
  return { value: 0, unit, breakdown: [], source: ['vetmanager'], note: 'Данных склада нет.' }
}

export function buildStock({ scenario, asOf, month }: { scenario: string; asOf: string | null; month: string | null }): StockReport {
  const common = { ...stockExample, ...(asOf ? { as_of: asOf } : {}), ...(month ? { month } : {}) }
  if (scenario === 'reportempty') {
    return {
      ...common,
      status: 'empty',
      partial_reasons: [],
      headline: undefined,
      stock_value: zeroFigure('rub'),
      frozen: zeroFigure('rub'),
      frozen_positions: zeroFigure('count'),
      idle_buckets: [],
      expiring_60d: zeroFigure('rub'),
      expiring: [],
      expired_on_hand: zeroFigure('rub'),
      expired_items: [],
      written_off_month: zeroFigure('rub'),
      written_off_norm: zeroFigure('rub'),
      written_off_items: [],
      turnover_days: zeroFigure('days'),
      data_as_of: null,
    }
  }
  if (scenario === 'reportpartial') {
    return { ...common, status: 'partial', partial_reasons: ['missing_expiry', 'short_history', 'stale_stock'], missing_expiry_count: 14 }
  }
  if (scenario === 'reportcalm') {
    return {
      ...common,
      headline: 'Склад в порядке: сроки не истекают, залежавшихся товаров нет.',
      frozen: zeroFigure('rub'),
      frozen_positions: zeroFigure('count'),
      idle_buckets: [],
      expiring_60d: zeroFigure('rub'),
      expiring: [],
      expired_on_hand: zeroFigure('rub'),
      expired_items: [],
      written_off_month: zeroFigure('rub'),
      written_off_items: [],
    }
  }
  return common
}
