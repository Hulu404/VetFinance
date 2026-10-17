// Obligations of the planning mocks: validation of the bodies by the codes of the contract, the objects made from a body, the
// totals. The mock server plays the part of the backend, so it may count; the client never does (CLAUDE.md, rule 1).
import type { Equipment, Loan, ObligationsReport } from '../api/types'
import { monthNameLower } from '../lib/dates'
import { formatMoney } from '../lib/format'
import { rubFigure } from './figures'
import { calendarExample, newPlanningId, obligationsExample, planning } from './planningStore'

const MAX_KOPECKS = 10_000_000_000
const NAME_LIMIT = 80
const MONTHS_IN_YEAR = 12
const PERCENT_DIVISOR = 1200
const PERCENT_BASE = 1000

export type Body = Record<string, unknown>
export type FieldErrors = Record<string, string>

const isInteger = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value)

function money(body: Body, name: string, errors: FieldErrors, options: { zero: boolean; required: boolean }): void {
  const value = body[name]
  if (value === undefined || value === null) {
    if (options.required) errors[name] = 'required'
    return
  }
  if (!isInteger(value)) errors[name] = 'invalid'
  else if (value < 0 || (value === 0 && !options.zero)) errors[name] = 'must_be_positive'
  else if (value > MAX_KOPECKS) errors[name] = 'too_large'
}

function text(body: Body, name: string, errors: FieldErrors, required: boolean): void {
  const value = body[name]
  if (value === undefined || value === null || value === '') {
    if (required) errors[name] = 'required'
    return
  }
  if (typeof value !== 'string') errors[name] = 'invalid'
  else if (value.length > NAME_LIMIT) errors[name] = 'too_long'
}

function range(body: Body, name: string, errors: FieldErrors, min: number, max: number): void {
  const value = body[name]
  if (value === undefined || value === null) {
    errors[name] = 'required'
    return
  }
  if (!isInteger(value) || value < min || value > max) errors[name] = 'out_of_range'
}

/** Interest of a month on the remaining debt, in kopecks (a loan with the rate in percent per year). */
export function monthlyInterest(remaining: number, ratePct: number): number {
  return Math.round((remaining * ratePct) / PERCENT_DIVISOR)
}

export interface ValidationResult {
  fields: FieldErrors
  /** Only for `payment_below_interest`: the interest of the month in kopecks. */
  interest?: number
}

/** Checks a body of `POST` (all fields) or `PATCH` (the subset, merged with the stored object by the caller). */
export function validateObligation(body: Body, today: string): ValidationResult {
  const fields: FieldErrors = {}
  const kind = body.kind
  if (kind !== 'loan' && kind !== 'lease' && kind !== 'equipment') {
    fields.kind = kind === undefined ? 'required' : 'invalid'
    return { fields }
  }
  text(body, 'name', fields, true)
  if (kind === 'equipment') {
    money(body, 'cost', fields, { zero: false, required: true })
    range(body, 'life_years', fields, 1, 30)
    const from = body.in_service_from
    if (typeof from !== 'string' || from === '') fields.in_service_from = 'required'
    else if (!/^\d{4}-\d{2}-\d{2}$/.test(from)) fields.in_service_from = 'invalid'
    else if (from > today) fields.in_service_from = 'in_future'
    return { fields }
  }
  text(body, 'lender', fields, false)
  money(body, 'principal', fields, { zero: false, required: true })
  money(body, 'remaining', fields, { zero: true, required: true })
  money(body, 'payment', fields, { zero: false, required: true })
  range(body, 'payment_day', fields, 1, 31)
  if (kind === 'loan') {
    const rate = body.rate_pct
    if (rate === undefined || rate === null) fields.rate_pct = 'required'
    else if (typeof rate !== 'number' || rate < 0 || rate > 100) fields.rate_pct = 'out_of_range'
    else if (Math.round(rate * 100) / 100 !== rate) fields.rate_pct = 'too_many_decimals'
  }
  if (!fields.remaining && !fields.principal && Number(body.remaining) > Number(body.principal)) fields.remaining = 'remaining_gt_principal'
  if (kind === 'loan' && !fields.payment && !fields.remaining && !fields.rate_pct) {
    const interest = monthlyInterest(Number(body.remaining), Number(body.rate_pct))
    if (Number(body.payment) <= interest && Number(body.remaining) > 0) return { fields: { ...fields, payment: 'payment_below_interest' }, interest }
  }
  return { fields }
}

export function buildLoan(body: Body, id: string): Loan {
  const kind = body.kind === 'lease' ? 'lease' : 'loan'
  const principal = Number(body.principal)
  const remaining = Number(body.remaining)
  const payment = Number(body.payment)
  const rate = kind === 'loan' ? Number(body.rate_pct) : null
  const paidPct = principal === 0 ? 0 : Math.round(((principal - remaining) / principal) * PERCENT_BASE) / 10
  const interest = rate === null ? 0 : monthlyInterest(remaining, rate)
  return {
    id,
    kind,
    name: String(body.name),
    lender: typeof body.lender === 'string' && body.lender !== '' ? body.lender : null,
    principal: rubFigure(principal, [['По договору', principal]], ['manual'], 'Внесено вручную.'),
    remaining: rubFigure(
      remaining,
      [
        ['По договору', principal],
        ['Выплачено', -(principal - remaining)],
      ],
      ['manual', 'calc'],
      kind === 'loan' ? 'Основной долг без будущих процентов.' : 'Сумма оставшихся платежей по договору.',
    ),
    paid_pct: {
      ...rubFigure(
        paidPct,
        [
          ['Выплачено', principal - remaining],
          ['По договору', principal],
        ],
        ['calc'],
        `${formatMoney(principal - remaining)} ÷ ${formatMoney(principal)} = ${String(paidPct).replace('.', ',')}%.`,
      ),
      unit: 'pct',
    },
    payment:
      kind === 'loan'
        ? rubFigure(
            payment,
            [
              ['Проценты за месяц', interest],
              ['Основной долг', payment - interest],
            ],
            ['manual', 'calc'],
            'Платёж по графику: проценты идут в расходы отчёта, основной долг нет.',
          )
        : rubFigure(payment, [['Платёж по лизингу', payment]], ['manual', 'calc'], 'В расходы отчёта «Прибыли и убытки» идёт целиком.'),
    rate_pct: rate,
    payment_day: Number(body.payment_day),
    next_payment_date: null,
    last_payment_month: '2028-10',
    status: remaining === 0 ? 'paid' : 'active',
    closed_from: null,
  }
}

export function buildEquipment(body: Body, id: string): Equipment {
  const cost = Number(body.cost)
  const years = Number(body.life_years)
  const months = years * MONTHS_IN_YEAR
  const monthly = Math.round(cost / months)
  const from = String(body.in_service_from)
  return {
    id,
    kind: 'equipment',
    name: String(body.name),
    cost: rubFigure(cost, [['Стоимость при покупке', cost]], ['manual'], 'Внесено вручную.'),
    life_years: years,
    in_service_from: from,
    amortization_from: from.slice(0, 7),
    amortization_to: from.slice(0, 7),
    monthly: {
      ...rubFigure(monthly, [[String(body.name), monthly]], ['calc'], `${formatMoney(cost)} ÷ ${months} = ${formatMoney(monthly)} в месяц.`),
      details: [
        { label: 'Стоимость', value: cost, unit: 'rub' },
        { label: 'Срок службы, месяцев', value: months, unit: 'count' },
      ],
    },
    status: 'active',
    closed_from: null,
  }
}

/** Month of "today" of the mock clinic: the example's month. */
export const currentMonth = obligationsExample.pnl_month.month

const ORDER = { active: 0, paid: 1, closed: 2 }

/** The closed obligation stays in the list: zero remaining and payment, the status and the month of closing. */
export function closeObligation(id: string): boolean {
  const loan = planning.loans.find((item) => item.id === id)
  const equipment = planning.equipment.find((item) => item.id === id)
  const zero = (figure: Loan['remaining']) => ({ ...figure, value: 0, breakdown: [] })
  if (loan && loan.status !== 'closed') {
    planning.loans = planning.loans.map((item) =>
      item.id === id ? { ...item, status: 'closed' as const, closed_from: currentMonth, remaining: zero(item.remaining), payment: zero(item.payment) } : item,
    )
    return true
  }
  if (equipment && equipment.status !== 'closed') {
    planning.equipment = planning.equipment.map((item) => (item.id === id ? { ...item, status: 'closed' as const, closed_from: currentMonth } : item))
    return true
  }
  return false
}

export function newObligationId(): string {
  return newPlanningId('obl')
}

/** The answer of `GET /v1/obligations` for the stored obligations: totals of the active ones, the list sorted by status. */
export function buildObligations(asOf: string | null): ObligationsReport {
  const loans = [...planning.loans].sort((a, b) => ORDER[a.status] - ORDER[b.status])
  const equipment = [...planning.equipment].sort((a, b) => ORDER[a.status] - ORDER[b.status])
  const activeLoans = loans.filter((loan) => loan.status === 'active')
  const activeEquipment = equipment.filter((item) => item.status === 'active')
  const base = obligationsExample
  const debt = activeLoans.reduce((total, loan) => total + loan.remaining.value, 0)
  const monthlyPayment = activeLoans.reduce((total, loan) => total + loan.payment.value, 0)
  const amortization = activeEquipment.reduce((total, item) => total + item.monthly.value, 0)
  const interest = activeLoans.filter((loan) => loan.kind === 'loan').reduce((total, loan) => total + monthlyInterest(loan.remaining.value, loan.rate_pct ?? 0), 0)
  const lease = activeLoans.filter((loan) => loan.kind === 'lease').reduce((total, loan) => total + loan.payment.value, 0)
  const unchanged =
    planning.loans.length === base.loans.length &&
    planning.equipment.length === base.equipment.length &&
    [...planning.loans, ...planning.equipment].every((item) => item.status === 'active') &&
    JSON.stringify(planning.loans) === JSON.stringify(base.loans) &&
    JSON.stringify(planning.equipment) === JSON.stringify(base.equipment)
  if (unchanged) return { ...structuredClone(base), as_of: asOf ?? base.as_of }
  return {
    as_of: asOf ?? base.as_of,
    debt_total: rubFigure(debt, activeLoans.map((loan): [string, number] => [loan.name, loan.remaining.value]), ['manual'], base.debt_total.note),
    monthly_payment: rubFigure(monthlyPayment, activeLoans.map((loan): [string, number] => [loan.name, loan.payment.value]), ['manual'], base.monthly_payment.note),
    amortization_month: rubFigure(amortization, activeEquipment.map((item): [string, number] => [item.name, item.monthly.value]), ['calc'], base.amortization_month.note),
    pnl_month: {
      month: base.pnl_month.month,
      amount: rubFigure(
        interest + lease + amortization,
        [
          ['Проценты по кредиту', interest],
          ['Лизинг (платёж целиком)', lease],
          ['Амортизация оборудования', amortization],
        ],
        ['calc'],
        `То же число в строке «Обязательства и амортизация» отчёта за ${monthNameLower(base.pnl_month.month)}. Основной долг кредита расходом не считается.`,
      ),
    },
    loans,
    equipment,
  }
}

/** Reference window of the calendar mock, to check the date of a manual payment. */
export const calendarWindow = calendarExample.window
