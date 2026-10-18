import { http, HttpResponse } from 'msw'
import type { EfficiencyReport, EfficiencySettings, RecipeItem, ServiceItem, ServiceList, ServiceRecipe } from '../api/types'
import { errorResponse, guard } from './guard'
import {
  applyRecipe,
  buildHeadline,
  cardFor,
  cardVariants,
  efficiencyExamples,
  manualRow,
  newServiceId,
  noRecipeCard,
  normalizeName,
  pricing,
  rowFromCard,
  stockCatalog,
} from './pricingStore'
import { getMockScenario } from './scenario'

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/
const NO_HOUR_COST_ID = '670666eb-c214-5d6b-865d-927f027d2c50'
const MAX_PAGE = 200
const MAX_ITEMS = 30
const MAX_KOPECKS = 10_000_000_000

const validation = (fields: Record<string, string>) => errorResponse(422, 'validation', 'Проверьте поля.', { fields })
const serverError = () => errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')

async function readBody(request: Request): Promise<Record<string, unknown>> {
  try {
    const parsed: unknown = await request.json()
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

async function priceGuard(request: Request, errorScenarios: string[]): Promise<Response | null> {
  const blocked = await guard(request)
  if (blocked) return blocked
  return errorScenarios.includes(getMockScenario()) ? serverError() : null
}

function visibleServices(): ServiceItem[] {
  const scenario = getMockScenario()
  if (scenario === 'priceempty') return []
  if (scenario === 'pricenorecipes') return pricing.services.map((item) => ({ ...item, status: 'no_recipe', margin_pct: null, monthly_profit: null }))
  return pricing.services
}

function sortValue(item: ServiceItem, sort: string): number | null {
  return (sort === 'profit' ? item.monthly_profit : item.margin_pct)?.value ?? null
}

function sortedRows(rows: ServiceItem[], sort: string, order: string): ServiceItem[] {
  const sign = order === 'desc' ? -1 : 1
  return [...rows].sort((a, b) => {
    const left = sortValue(a, sort)
    const right = sortValue(b, sort)
    if (left === null || right === null) {
      if (left === right) return a.name.localeCompare(b.name, 'ru')
      return left === null ? 1 : -1
    }
    return left === right ? a.name.localeCompare(b.name, 'ru') : sign * (left - right)
  })
}

function listFields(url: URL): Record<string, string> {
  const fields: Record<string, string> = {}
  const { searchParams } = url
  if (!['margin', 'profit', null].includes(searchParams.get('sort'))) fields.sort = 'invalid'
  if (!['asc', 'desc', null].includes(searchParams.get('order'))) fields.order = 'invalid'
  if (!['all', 'loss', 'no_recipe', null].includes(searchParams.get('filter'))) fields.filter = 'invalid'
  const asOf = searchParams.get('as_of')
  if (asOf !== null && !DATE_PATTERN.test(asOf)) fields.as_of = 'invalid'
  const limit = searchParams.get('limit')
  if (limit !== null && (!/^\d+$/.test(limit) || Number(limit) < 1)) fields.limit = 'must_be_positive'
  else if (limit !== null && Number(limit) > MAX_PAGE) fields.limit = 'too_large'
  return fields
}

function buildList(url: URL): ServiceList {
  const { searchParams } = url
  const all = visibleServices()
  const filter = searchParams.get('filter') ?? 'all'
  const needle = normalizeName(searchParams.get('q') ?? '')
  const matching = all.filter((item) => {
    if (filter === 'loss' && !((item.margin_pct?.value ?? 0) < 0)) return false
    if (filter === 'no_recipe' && item.status !== 'no_recipe') return false
    return needle === '' || normalizeName(item.name).includes(needle)
  })
  const rows = sortedRows(matching, searchParams.get('sort') ?? 'margin', searchParams.get('order') ?? 'asc')
  const limit = Number(searchParams.get('limit') ?? 50)
  const start = Number(searchParams.get('cursor') ?? 0)
  const page = rows.slice(start, start + limit)
  const headline = buildHeadline(all)
  return {
    basis_month: '2026-09',
    ...(headline ? { headline } : {}),
    counts: {
      all: all.length,
      loss: all.filter((item) => (item.margin_pct?.value ?? 0) < 0).length,
      no_recipe: all.filter((item) => item.status === 'no_recipe').length,
    },
    items: page,
    next_cursor: start + limit < rows.length ? String(start + limit) : null,
  }
}

function recipeOf(id: string): ServiceRecipe | null {
  const stored = pricing.recipes[id]
  if (stored) return stored
  const row = pricing.services.find((item) => item.id === id)
  if (!row) return null
  const template = Object.values(pricing.recipes).find((recipe) => !recipe.has_recipe)
  if (!template) return null
  return { ...template, service: { id: row.id, name: row.name } }
}

function recipeFields(body: Record<string, unknown>): Record<string, string> {
  const fields: Record<string, string> = {}
  const { minutes, doctor_pct: pct, items } = body
  if (minutes !== undefined && minutes !== null) {
    if (typeof minutes !== 'number' || !Number.isInteger(minutes)) fields.minutes = 'invalid'
    else if (minutes < 1 || minutes > 1440) fields.minutes = 'out_of_range'
  }
  if (pct !== undefined && pct !== null) {
    if (typeof pct !== 'number') fields.doctor_pct = 'invalid'
    else if (pct < 0 || pct > 100) fields.doctor_pct = 'out_of_range'
    else if (Math.round(pct * 100) !== pct * 100) fields.doctor_pct = 'too_many_decimals'
  }
  if (!Array.isArray(items)) fields.items = 'required'
  else if (items.length > MAX_ITEMS) fields.items = 'out_of_range'
  else Object.assign(fields, itemFields(items as Record<string, unknown>[]))
  return fields
}

function itemFields(items: Record<string, unknown>[]): Record<string, string> {
  const fields: Record<string, string> = {}
  const known = new Set(stockCatalog().map((item) => item.id))
  const seen = new Set<string>()
  items.forEach((item, index) => {
    const at = (name: string) => `items.${index}.${name}`
    const id = item.item_id
    if (typeof id !== 'string' || id === '') fields[at('item_id')] = 'required'
    else if (!known.has(id)) fields[at('item_id')] = 'unknown_item'
    else if (seen.has(id)) fields[at('item_id')] = 'duplicate_item'
    else seen.add(id)
    if (!['drugs', 'anesthesia', 'supplies'].includes(String(item.group))) fields[at('group')] = item.group === undefined ? 'required' : 'invalid'
    const qty = item.qty
    if (qty === undefined || qty === null) fields[at('qty')] = 'required'
    else if (typeof qty !== 'number') fields[at('qty')] = 'invalid'
    else if (qty <= 0) fields[at('qty')] = 'must_be_positive'
    else if (Math.round(qty * 1000) !== qty * 1000) fields[at('qty')] = 'too_many_decimals'
  })
  return fields
}

function serviceFields(body: Record<string, unknown>, selfId: string | null, partial: boolean): Record<string, string> {
  const fields: Record<string, string> = {}
  const { name, group, price } = body
  if (!partial || name !== undefined) {
    if (typeof name !== 'string' || name.trim() === '') fields.name = 'required'
    else if (name.trim().length > 120) fields.name = 'too_long'
    else if (pricing.services.some((item) => item.id !== selfId && normalizeName(item.name) === normalizeName(name))) fields.name = 'duplicate_name'
  }
  if (typeof group === 'string' && group.length > 80) fields.group = 'too_long'
  if (!partial || price !== undefined) {
    if (price === undefined || price === null) fields.price = 'required'
    else if (typeof price !== 'number' || !Number.isInteger(price)) fields.price = 'invalid'
    else if (price <= 0) fields.price = 'must_be_positive'
    else if (price > MAX_KOPECKS) fields.price = 'too_large'
  }
  return fields
}

const servicesHandlers = [
  http.get('*/v1/services', async ({ request }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror'])
    if (blocked) return blocked
    const url = new URL(request.url)
    const fields = listFields(url)
    if (Object.keys(fields).length > 0) return validation(fields)
    return HttpResponse.json(buildList(url))
  }),

  http.post('*/v1/services', async ({ request }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror'])
    if (blocked) return blocked
    const body = await readBody(request)
    const fields = serviceFields(body, null, false)
    if (Object.keys(fields).length > 0) return validation(fields)
    const group = typeof body.group === 'string' && body.group.trim() !== '' ? body.group.trim() : null
    const row = manualRow(newServiceId(), String(body.name).trim(), group, Number(body.price))
    pricing.services = [...pricing.services, row]
    return HttpResponse.json(row, { status: 201 })
  }),

  http.patch('*/v1/services/:id', async ({ request, params }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror'])
    if (blocked) return blocked
    const id = String(params.id)
    const row = pricing.services.find((item) => item.id === id)
    if (!row) return errorResponse(404, 'not_found', 'Услуга не найдена.')
    if (row.source !== 'manual') return errorResponse(403, 'forbidden', 'Услугу из Ветменеджера менять нельзя.')
    const body = await readBody(request)
    const fields = serviceFields(body, id, true)
    if (Object.keys(fields).length > 0) return validation(fields)
    const price = typeof body.price === 'number' ? body.price : row.price.value
    const next = manualRow(id, typeof body.name === 'string' ? body.name.trim() : row.name, 'group' in body ? String(body.group ?? '').trim() || null : row.group, price)
    pricing.services = pricing.services.map((item) => (item.id === id ? { ...next, status: item.status, margin_pct: item.margin_pct, monthly_profit: item.monthly_profit } : item))
    return new HttpResponse(null, { status: 204 })
  }),

  http.delete('*/v1/services/:id', async ({ request, params }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror'])
    if (blocked) return blocked
    const id = String(params.id)
    const row = pricing.services.find((item) => item.id === id)
    if (!row) return errorResponse(404, 'not_found', 'Услуга не найдена.')
    if (row.source !== 'manual') return errorResponse(403, 'forbidden', 'Услугу из Ветменеджера удалить нельзя.')
    pricing.services = pricing.services.filter((item) => item.id !== id)
    delete pricing.recipes[id]
    delete pricing.cards[id]
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('*/v1/services/:id/cost', async ({ request, params }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror', 'pricecarderror'])
    if (blocked) return blocked
    const id = String(params.id)
    const row = pricing.services.find((item) => item.id === id)
    if (!row) return errorResponse(404, 'not_found', 'Услуга не найдена.')
    const scenario = getMockScenario()
    if (scenario === 'pricenorecipes') return HttpResponse.json(noRecipeCard(row))
    if (scenario === 'pricenohourcost' && id === NO_HOUR_COST_ID) return HttpResponse.json(cardVariants.no_hour_cost)
    return HttpResponse.json(cardFor(id))
  }),

  http.get('*/v1/services/:id/recipe', async ({ request, params }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror'])
    if (blocked) return blocked
    const recipe = recipeOf(String(params.id))
    return recipe ? HttpResponse.json(recipe) : errorResponse(404, 'not_found', 'Услуга не найдена.')
  }),

  http.put('*/v1/services/:id/recipe', async ({ request, params }) => {
    const blocked = await priceGuard(request, ['error', 'priceerror'])
    if (blocked) return blocked
    const id = String(params.id)
    const row = pricing.services.find((item) => item.id === id)
    const card = cardFor(id)
    const current = recipeOf(id)
    if (!row || !card || !current) return errorResponse(404, 'not_found', 'Услуга не найдена.')
    const body = await readBody(request)
    const fields = recipeFields(body)
    if (Object.keys(fields).length > 0) return validation(fields)
    const catalog = new Map(stockCatalog().map((item) => [item.id, item]))
    const items = (body.items as Record<string, unknown>[]).map((entry): RecipeItem => {
      const stock = catalog.get(String(entry.item_id))
      return {
        item_id: String(entry.item_id),
        name: stock?.name ?? '',
        unit: stock?.unit ?? '',
        group: entry.group as RecipeItem['group'],
        qty: Number(entry.qty),
        unit_cost: stock?.unit_cost ?? null,
      }
    })
    const saved: ServiceRecipe = {
      ...current,
      has_recipe: true,
      minutes: typeof body.minutes === 'number' ? body.minutes : null,
      doctor_pct: typeof body.doctor_pct === 'number' ? body.doctor_pct : null,
      items,
    }
    const nextCard = applyRecipe(card, saved)
    pricing.recipes[id] = saved
    pricing.cards[id] = nextCard
    pricing.services = pricing.services.map((item) => (item.id === id ? rowFromCard(item, nextCard) : item))
    return HttpResponse.json(saved)
  }),

  http.get('*/v1/stock/items', async ({ request }) => {
    const blocked = await priceGuard(request, ['error'])
    if (blocked) return blocked
    const url = new URL(request.url)
    const needle = normalizeName(url.searchParams.get('q') ?? '')
    const items = stockCatalog().filter((item) => needle === '' || normalizeName(item.name).includes(needle))
    return HttpResponse.json({ items, next_cursor: null })
  }),
]


function efficiencyFor(month: string | null): EfficiencyReport {
  const scenario = getMockScenario()
  const complete = pricing.hoursSaved
  const key =
    scenario === 'effward' || ((scenario === 'effnohours' || scenario === 'effdoctornohours') && complete)
      ? 'ward_no_schedule'
      : scenario === 'effnohours'
        ? 'no_hours'
        : scenario === 'effdoctornohours'
          ? 'doctor_no_hours'
          : scenario === 'effnoexpenses'
            ? 'no_expenses'
            : 'main'
  const example = efficiencyExamples[key] as EfficiencyReport
  const shown = month ?? example.month
  const base: EfficiencyReport = { ...example, month: shown, period: { ...example.period, month: shown } }
  if (scenario !== 'effempty') return base
  const { headline, ...rest } = base
  void headline
  return {
    ...rest,
    status: 'empty',
    visits: { ...base.visits, value: 0, breakdown: [] },
    load_pct: null,
    avg_check: null,
    rooms: [],
    doctors: [],
    hour_cost: null,
    hour_margin: null,
    hour_cost_parts: [],
  }
}

/** The settings as the scenario wants them: before the first save "no hours" means that no doctor has hours. */
function settingsView(): EfficiencySettings {
  const scenario = getMockScenario()
  if (pricing.hoursSaved) return pricing.settings
  if (scenario === 'effnohours') return { ...pricing.settings, doctors: pricing.settings.doctors.map((doctor) => ({ ...doctor, hours_per_week: null })) }
  if (scenario === 'effdoctornohours') {
    return { ...pricing.settings, doctors: pricing.settings.doctors.map((doctor, index, all) => (index === all.length - 1 ? { ...doctor, hours_per_week: null } : doctor)) }
  }
  return pricing.settings
}

function settingsFields(body: Record<string, unknown>): Record<string, string> {
  const fields: Record<string, string> = {}
  const minutes = body.avg_visit_minutes
  if (minutes === undefined || minutes === null) fields.avg_visit_minutes = 'required'
  else if (typeof minutes !== 'number' || !Number.isInteger(minutes)) fields.avg_visit_minutes = 'invalid'
  else if (minutes < 5 || minutes > 240) fields.avg_visit_minutes = 'out_of_range'
  const doctors = body.doctors
  if (Array.isArray(doctors)) {
    ;(doctors as Record<string, unknown>[]).forEach((doctor, index) => {
      const hours = doctor.hours_per_week
      const at = `doctors.${index}.hours_per_week`
      if (!pricing.settings.doctors.some((known) => known.id === doctor.id)) fields[`doctors.${index}.id`] = 'invalid'
      if (hours === undefined || hours === null) return
      if (typeof hours !== 'number') fields[at] = 'invalid'
      else if (hours < 0 || hours > 80) fields[at] = 'out_of_range'
      else if (Math.round(hours * 10) !== hours * 10) fields[at] = 'too_many_decimals'
      else if (Math.round(hours * 2) !== hours * 2) fields[at] = 'invalid'
    })
  }
  return fields
}

const efficiencyHandlers = [
  http.get('*/v1/efficiency', async ({ request }) => {
    const blocked = await priceGuard(request, ['error', 'efferror'])
    if (blocked) return blocked
    const url = new URL(request.url)
    const asOf = url.searchParams.get('as_of')
    if (asOf !== null && !DATE_PATTERN.test(asOf)) return validation({ as_of: 'invalid' })
    const month = url.searchParams.get('month')
    if (month !== null && !MONTH_PATTERN.test(month)) return validation({ month: 'invalid' })
    if (month !== null && month > efficiencyExamples.main!.month) return validation({ month: 'in_future' })
    return HttpResponse.json(efficiencyFor(month))
  }),

  http.get('*/v1/efficiency/settings', async ({ request }) => {
    const blocked = await priceGuard(request, ['error', 'efferror'])
    return blocked ?? HttpResponse.json(settingsView())
  }),

  http.put('*/v1/efficiency/settings', async ({ request }) => {
    const blocked = await priceGuard(request, ['error', 'efferror'])
    if (blocked) return blocked
    const body = await readBody(request)
    const fields = settingsFields(body)
    if (Object.keys(fields).length > 0) return validation(fields)
    const changes = new Map((Array.isArray(body.doctors) ? (body.doctors as Record<string, unknown>[]) : []).map((doctor) => [String(doctor.id), doctor.hours_per_week]))
    pricing.settings = {
      avg_visit_minutes: Number(body.avg_visit_minutes),
      doctors: pricing.settings.doctors.map((doctor) =>
        changes.has(doctor.id) ? { ...doctor, hours_per_week: typeof changes.get(doctor.id) === 'number' ? Number(changes.get(doctor.id)) : null } : doctor,
      ),
    }
    pricing.hoursSaved = true
    return HttpResponse.json(pricing.settings)
  }),
]

export const pricingHandlers = [...servicesHandlers, ...efficiencyHandlers]
