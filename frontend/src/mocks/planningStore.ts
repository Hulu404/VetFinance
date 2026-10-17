// State and builders of the planning mocks (calendar, obligations). The base is the example of the contract (golden set 5,
// `backend/openapi.json`). The mock server plays the part of the backend: it may add and compare numbers, the client never does
// (CLAUDE.md, rule 1). Only what a change of data needs is recomputed; the alerts stay those of the example.
import type {
  Advice,
  CalendarDay,
  CalendarPayment,
  CalendarReport,
  Equipment,
  Figure,
  Loan,
  ManualPayment,
  ObligationsReport,
  PaymentSource,
} from '../api/types'
import { formatDayMonth } from '../lib/dates'
import { formatMoney } from '../lib/format'
import { rubFigure } from './figures'
import data from './data/planning_set05.json'
import type { MockScenario } from './scenario'

interface PlanningExamples {
  calendar: CalendarReport
  obligations: ObligationsReport
  manual_payment: ManualPayment
  counterparty: { id: string; name: string; max_deferral_days: number }
  cash_gap_advice: Advice
}

const examples = data as unknown as PlanningExamples

export const cashGapAdvice = examples.cash_gap_advice
export const calendarExample = examples.calendar
export const obligationsExample = examples.obligations

const NO_SUGGESTION_TEXT =
  'Перенос одного платежа разрыв не закрывает. Если поставщик согласен подождать, укажите отсрочку у его платежа.'
const PARTIAL_SUGGESTION_TEXT =
  'Перенос платежа ООО «Зоовет» на 108 500 ₽ с 7 октября на 12 октября уменьшит разрыв, но не закроет его.'

export interface AddedPayment {
  id: string
  date: string
  name: string
  amount: number
  categoryId: string | null
  maxDeferralDays: number
}

interface PlanningState {
  /** Kopecks; changed by `PATCH /v1/clinic`. */
  safeBalance: number
  manual: AddedPayment[]
  /** `counterparty.id` -> days. */
  deferrals: Record<string, number>
  loans: Loan[]
  equipment: Equipment[]
  nextId: number
}

function initialState(): PlanningState {
  return {
    safeBalance: calendarExample.safe_balance.value,
    manual: [],
    deferrals: {},
    loans: structuredClone(obligationsExample.loans),
    equipment: structuredClone(obligationsExample.equipment),
    nextId: 1,
  }
}

export const planning: PlanningState = initialState()

export function resetPlanningState(): void {
  Object.assign(planning, initialState())
}

export function newPlanningId(prefix: string): string {
  const id = `${prefix}-${planning.nextId}`
  planning.nextId += 1
  return id
}

// ------------------------------------------------------------------ calendar

function isDirty(): boolean {
  return (
    planning.manual.length > 0 ||
    planning.safeBalance !== calendarExample.safe_balance.value ||
    Object.keys(planning.deferrals).length > 0
  )
}

function manualPayment(added: AddedPayment): CalendarPayment {
  const amount = rubFigure(added.amount, [[added.name, added.amount]], ['manual'], 'Платёж внесён вручную.')
  return {
    id: added.id,
    name: added.name,
    category: null,
    counterparty: null,
    amount,
    source: 'manual',
    balance_after: amount,
    max_deferral_days: added.maxDeferralDays,
  }
}

function byAmountThenName(a: CalendarPayment, b: CalendarPayment): number {
  return b.amount.value - a.amount.value || a.name.localeCompare(b.name, 'ru')
}

function belowSafe(closing: number, safe: number): boolean {
  return safe > 0 ? closing < safe : false
}

/** Walks the days in order: balance after each payment, evening balance, status, note. */
function recompute(report: CalendarReport): void {
  const safe = report.safe_balance.value
  let balance = report.days[0]?.opening.value ?? 0
  report.days.forEach((day: CalendarDay, index: number) => {
    if (index > 0) {
      const previous = report.days[index - 1]
      day.opening = rubFigure(
        balance,
        [[`Остаток на вечер ${formatDayMonth(previous?.date ?? day.date)}`, balance]],
        ['calc'],
        'Остаток на вечер предыдущего дня.',
      )
    }
    day.payments.sort(byAmountThenName)
    let running = balance
    let negative = false
    for (const payment of day.payments) {
      const before = running
      running -= payment.amount.value
      negative = negative || running < 0
      payment.balance_after = rubFigure(
        running,
        [
          ['До платежа', before],
          [payment.name, -payment.amount.value],
        ],
        ['calc'],
        'Выручку дня считаем после платежей: деньги приходят в течение дня.',
      )
    }
    const closing = running + day.income_forecast.value
    const status: CalendarDay['status'] = negative || closing < 0 ? 'below_zero' : belowSafe(closing, safe) ? 'below_safe' : 'ok'
    day.status = status
    day.note =
      status === 'ok'
        ? `Запас соблюдён: остаток выше ${formatMoney(safe)}.`
        : `Остаток на вечер ниже безопасного запаса на ${formatMoney(safe - closing)}.`
    day.closing = rubFigure(
      closing,
      [
        ['На утро', balance],
        ...day.payments.map((payment): [string, number] => [payment.name, -payment.amount.value]),
        ['Выручка, прогноз', day.income_forecast.value],
      ],
      ['calc'],
      day.note,
    )
    balance = closing
  })
}

function sumBySource(report: CalendarReport, source: PaymentSource): number {
  return report.days.flatMap((day) => day.payments).filter((payment) => payment.source === source).reduce((total, payment) => total + payment.amount.value, 0)
}

function recomputeSummary(report: CalendarReport): void {
  const payments = report.days.flatMap((day) => day.payments)
  const expense = payments.reduce((total, payment) => total + payment.amount.value, 0)
  report.summary.expense = rubFigure(
    expense,
    [
      ['Регулярные платежи', sumBySource(report, 'recurring')],
      ['Обязательства', sumBySource(report, 'obligation')],
      ['Внесено вручную', sumBySource(report, 'manual')],
    ],
    ['bank', 'manual'],
    `${payments.length} платежей: аренда, зарплата, поставщики, налоги, кредит и лизинг.`,
  )
  report.summary.payments_count = payments.length
  const lowest = report.days.reduce((best, day) => (day.closing.value < best.closing.value ? day : best), report.days[0] as CalendarDay)
  report.summary.lowest = { date: lowest.date, balance: lowest.closing, status: lowest.status }
}

function withSafeBalance(report: CalendarReport, safe: number): void {
  const figure: Figure = rubFigure(safe, [['Задан в настройках', safe]], ['manual'], report.safe_balance.note)
  report.safe_balance = figure
  report.safe_balance_set = safe > 0
}

function applyDeferrals(report: CalendarReport): void {
  for (const day of report.days) {
    for (const payment of day.payments) {
      const days = payment.counterparty ? planning.deferrals[payment.counterparty.id] : undefined
      if (days !== undefined) payment.max_deferral_days = days
    }
  }
}

function applyScenario(report: CalendarReport, scenario: MockScenario): void {
  const alert = report.alerts[0]
  switch (scenario) {
    case 'calnogap':
      report.alerts = []
      for (const day of report.days) day.status = 'ok'
      report.summary.lowest.status = 'ok'
      break
    case 'calpartialgap':
      if (alert?.suggestion) alert.suggestion = { ...alert.suggestion, closes_gap: false, text: PARTIAL_SUGGESTION_TEXT }
      break
    case 'calnosuggest':
      if (alert) {
        alert.suggestion = null
        alert.text = `${alert.text} ${NO_SUGGESTION_TEXT}`
      }
      break
    case 'calpartial':
      report.status = 'partial'
      report.partial_reasons = ['short_history', 'obligations_missing', 'no_bank']
      report.history_days = 34
      break
    case 'calempty':
      report.status = 'empty'
      report.partial_reasons = []
      report.history_days = 0
      report.data_as_of = null
      break
    default:
  }
}

/** The calendar answer for the current state of the mock and the chosen scenario. */
export function buildCalendar(scenario: MockScenario, asOf: string | null): CalendarReport {
  const report = structuredClone(calendarExample)
  if (asOf) report.as_of = asOf
  applyDeferrals(report)
  if (isDirty()) {
    withSafeBalance(report, planning.safeBalance)
    for (const added of planning.manual) report.days.find((day) => day.date === added.date)?.payments.push(manualPayment(added))
    recompute(report)
    recomputeSummary(report)
    if (!report.days.some((day) => day.status !== 'ok')) report.alerts = []
  }
  if (scenario === 'calnosafe') {
    withSafeBalance(report, 0)
    recompute(report)
    recomputeSummary(report)
    if (!report.days.some((day) => day.status !== 'ok')) report.alerts = []
  }
  applyScenario(report, scenario)
  return report
}

/** `cash_gap` for the dashboard: the first alert of the calendar, with its suggestion in the text. */
export function cashGapFromCalendar(report: CalendarReport): typeof cashGapAdvice | null {
  const alert = report.alerts[0]
  if (!alert) return null
  return {
    ...cashGapAdvice,
    severity: alert.severity,
    title: alert.title,
    text: alert.suggestion ? `${alert.text} ${alert.suggestion.text}` : alert.text,
    why: alert.why,
    link: { path: '/planning/calendar', date: alert.date },
  }
}
