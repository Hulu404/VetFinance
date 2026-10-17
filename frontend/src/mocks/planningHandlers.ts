import { http, HttpResponse } from 'msw'
import type { Equipment, Loan } from '../api/types'
import { errorResponse, guard } from './guard'
import {
  buildEquipment,
  buildLoan,
  buildObligations,
  calendarWindow,
  closeObligation,
  newObligationId,
  validateObligation,
  type Body,
} from './obligationsMock'
import { clinicA } from './fixtures'
import { buildCalendar, calendarExample, newPlanningId, planning, type AddedPayment } from './planningStore'
import { getMockScenario } from './scenario'

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const MAX_DEFERRAL = 30
const MAX_KOPECKS = 10_000_000_000
const NAME_LIMIT = 80
/** Reference "today" of the mock clinic (the first day of the example window). */
const TODAY = calendarExample.window.from

async function planningGuard(request: Request, errorScenarios: string[]): Promise<Response | null> {
  const blocked = await guard(request)
  if (blocked) return blocked
  if (errorScenarios.includes(getMockScenario())) return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
  return null
}

async function readBody(request: Request): Promise<Body> {
  try {
    const parsed: unknown = await request.json()
    return typeof parsed === 'object' && parsed !== null ? (parsed as Body) : {}
  } catch {
    return {}
  }
}

const validation = (fields: Record<string, string>, extra: Record<string, unknown> = {}) =>
  errorResponse(422, 'validation', 'Проверьте поля.', { fields, ...extra })

function paymentFields(body: Body): Record<string, string> {
  const fields: Record<string, string> = {}
  const { name, amount, date, max_deferral_days: deferral } = body
  if (typeof name !== 'string' || name.trim() === '') fields.name = 'required'
  else if (name.length > NAME_LIMIT) fields.name = 'too_long'
  if (amount === undefined || amount === null) fields.amount = 'required'
  else if (typeof amount !== 'number' || !Number.isInteger(amount)) fields.amount = 'invalid'
  else if (amount <= 0) fields.amount = 'must_be_positive'
  else if (amount > MAX_KOPECKS) fields.amount = 'too_large'
  if (typeof date !== 'string' || date === '') fields.date = 'required'
  else if (!DATE_PATTERN.test(date)) fields.date = 'invalid'
  else if (date < calendarWindow.from || date > calendarWindow.to) fields.date = 'out_of_window'
  if (deferral !== undefined && deferral !== null) {
    if (typeof deferral !== 'number' || !Number.isInteger(deferral)) fields.max_deferral_days = 'invalid'
    else if (deferral < 0 || deferral > MAX_DEFERRAL) fields.max_deferral_days = 'out_of_range'
  }
  return fields
}

const MANUAL_ID_PREFIX = 'manual'

export const planningHandlers = [
  http.get('*/v1/calendar', async ({ request }) => {
    const blocked = await planningGuard(request, ['error', 'calerror'])
    if (blocked) return blocked
    const url = new URL(request.url)
    const days = url.searchParams.get('days')
    if (days !== null && days !== '22') return validation({ days: 'invalid' })
    const asOf = url.searchParams.get('as_of')
    if (asOf !== null && !DATE_PATTERN.test(asOf)) return validation({ as_of: 'invalid' })
    return HttpResponse.json(buildCalendar(getMockScenario(), asOf))
  }),

  http.post('*/v1/calendar/payments', async ({ request }) => {
    const blocked = await planningGuard(request, ['error', 'calerror'])
    if (blocked) return blocked
    const body = await readBody(request)
    const fields = paymentFields(body)
    if (Object.keys(fields).length > 0) return validation(fields)
    const added: AddedPayment = {
      id: newPlanningId(MANUAL_ID_PREFIX),
      date: String(body.date),
      name: String(body.name).trim(),
      amount: Number(body.amount),
      categoryId: typeof body.category_id === 'string' ? body.category_id : null,
      maxDeferralDays: typeof body.max_deferral_days === 'number' ? body.max_deferral_days : 0,
    }
    planning.manual.push(added)
    return HttpResponse.json(
      {
        id: added.id,
        date: added.date,
        name: added.name,
        category: null,
        amount: { value: added.amount, unit: 'rub', breakdown: [{ label: added.name, value: added.amount, unit: 'rub' }], source: ['manual'], note: 'Платёж внесён вручную.' },
        source: 'manual',
        max_deferral_days: added.maxDeferralDays,
      },
      { status: 201 },
    )
  }),

  http.delete('*/v1/calendar/payments/:id', async ({ request, params }) => {
    const blocked = await planningGuard(request, ['error', 'calerror'])
    if (blocked) return blocked
    const id = String(params.id)
    if (!planning.manual.some((item) => item.id === id)) return errorResponse(404, 'not_found', 'Платёж не найден.')
    planning.manual = planning.manual.filter((item) => item.id !== id)
    return new HttpResponse(null, { status: 204 })
  }),

  http.patch('*/v1/counterparties/:id', async ({ request, params }) => {
    const blocked = await planningGuard(request, ['error', 'calerror'])
    if (blocked) return blocked
    const id = String(params.id)
    const counterparties = calendarExample.days.flatMap((day) => day.payments).flatMap((payment) => (payment.counterparty ? [payment.counterparty] : []))
    const found = counterparties.find((item) => item.id === id)
    if (!found) return errorResponse(404, 'not_found', 'Контрагент не найден.')
    const days = (await readBody(request)).max_deferral_days
    if (days === undefined || days === null) return validation({ max_deferral_days: 'required' })
    if (typeof days !== 'number' || !Number.isInteger(days)) return validation({ max_deferral_days: 'invalid' })
    if (days < 0 || days > MAX_DEFERRAL) return validation({ max_deferral_days: 'out_of_range' })
    planning.deferrals[id] = days
    return HttpResponse.json({ id, name: found.name, max_deferral_days: days })
  }),

  http.patch('*/v1/clinic', async ({ request }) => {
    const blocked = await planningGuard(request, ['error'])
    if (blocked) return blocked
    const body = await readBody(request)
    const unknown = Object.keys(body).filter((key) => !['name', 'legal_entity', 'tax_regime', 'timezone', 'safe_balance'].includes(key))
    if (unknown.length > 0) return validation(Object.fromEntries(unknown.map((key) => [key, 'unknown_field'])))
    const safe = body.safe_balance
    if (safe !== undefined && safe !== null) {
      if (typeof safe !== 'number' || !Number.isInteger(safe)) return validation({ safe_balance: 'invalid' })
      if (safe < 0) return validation({ safe_balance: 'must_be_positive' })
      if (safe > MAX_KOPECKS) return validation({ safe_balance: 'too_large' })
      planning.safeBalance = safe
    }
    return HttpResponse.json(clinicNow())
  }),

  http.get('*/v1/obligations', async ({ request }) => {
    const blocked = await planningGuard(request, ['error', 'oblerror'])
    if (blocked) return blocked
    const asOf = new URL(request.url).searchParams.get('as_of')
    if (asOf !== null && !DATE_PATTERN.test(asOf)) return validation({ as_of: 'invalid' })
    if (getMockScenario() === 'oblempty') {
      const empty = buildObligations(asOf)
      return HttpResponse.json({
        ...empty,
        loans: [],
        equipment: [],
        debt_total: { ...empty.debt_total, value: 0, breakdown: [{ label: 'Нет кредитов и лизинга', value: 0, unit: 'rub' as const }] },
        monthly_payment: { ...empty.monthly_payment, value: 0, breakdown: [{ label: 'Нет кредитов и лизинга', value: 0, unit: 'rub' as const }] },
        amortization_month: { ...empty.amortization_month, value: 0, breakdown: [{ label: 'Нет оборудования', value: 0, unit: 'rub' as const }] },
        pnl_month: { ...empty.pnl_month, amount: { ...empty.pnl_month.amount, value: 0, breakdown: [] } },
      })
    }
    return HttpResponse.json(buildObligations(asOf))
  }),

  http.post('*/v1/obligations', async ({ request }) => {
    const blocked = await planningGuard(request, ['error', 'oblerror'])
    if (blocked) return blocked
    const body = await readBody(request)
    const result = validateObligation(body, TODAY)
    if (Object.keys(result.fields).length > 0) {
      return validation(result.fields, result.interest === undefined ? {} : { interest: result.interest })
    }
    const id = newObligationId()
    if (body.kind === 'equipment') {
      const equipment: Equipment = buildEquipment(body, id)
      planning.equipment = [...planning.equipment, equipment]
      return HttpResponse.json(equipment, { status: 201 })
    }
    const loan: Loan = buildLoan(body, id)
    planning.loans = [...planning.loans, loan]
    return HttpResponse.json(loan, { status: 201 })
  }),

  http.patch('*/v1/obligations/:id', async ({ request, params }) => {
    const blocked = await planningGuard(request, ['error', 'oblerror'])
    if (blocked) return blocked
    const id = String(params.id)
    const loan = planning.loans.find((item) => item.id === id && item.status !== 'closed')
    const equipment = planning.equipment.find((item) => item.id === id && item.status !== 'closed')
    if (!loan && !equipment) return errorResponse(404, 'not_found', 'Обязательство не найдено.')
    const body = await readBody(request)
    const stored = loan ?? equipment
    if (body.kind !== undefined && body.kind !== stored?.kind) return validation({ kind: 'invalid' })
    if (loan) {
      const merged: Body = {
        kind: loan.kind,
        name: loan.name,
        lender: loan.lender,
        principal: loan.principal.value,
        remaining: loan.remaining.value,
        payment: loan.payment.value,
        payment_day: loan.payment_day,
        rate_pct: loan.rate_pct,
        ...body,
      }
      const result = validateObligation(merged, TODAY)
      if (Object.keys(result.fields).length > 0) return validation(result.fields, result.interest === undefined ? {} : { interest: result.interest })
      const next = buildLoan(merged, id)
      planning.loans = planning.loans.map((item) => (item.id === id ? next : item))
      return HttpResponse.json(next)
    }
    if (equipment) {
      const merged: Body = {
        kind: 'equipment',
        name: equipment.name,
        cost: equipment.cost.value,
        life_years: equipment.life_years,
        in_service_from: equipment.in_service_from,
        ...body,
      }
      const result = validateObligation(merged, TODAY)
      if (Object.keys(result.fields).length > 0) return validation(result.fields)
      const next = buildEquipment(merged, id)
      planning.equipment = planning.equipment.map((item) => (item.id === id ? next : item))
      return HttpResponse.json(next)
    }
    return errorResponse(404, 'not_found', 'Обязательство не найдено.')
  }),

  http.delete('*/v1/obligations/:id', async ({ request, params }) => {
    const blocked = await planningGuard(request, ['error', 'oblerror'])
    if (blocked) return blocked
    if (!closeObligation(String(params.id))) return errorResponse(404, 'not_found', 'Обязательство не найдено.')
    return new HttpResponse(null, { status: 204 })
  }),
]

/** The clinic with the safe balance the calendar works with. */
export function clinicNow() {
  return { ...clinicA, safe_balance: planning.safeBalance }
}
