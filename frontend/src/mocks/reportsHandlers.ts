import { delay, http, HttpResponse } from 'msw'
import type { StockIdleItem, StockIdlePage } from '../api/types'
import { errorResponse, guard } from './guard'
import {
  buildNorm,
  buildPnl,
  buildStock,
  DEFAULT_AS_OF,
  lastClosedMonth,
  monthOfDate,
  OPEN_AS_OF,
  stockIdleExample,
} from './reportsFixtures'
import { getMockScenario } from './scenario'

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const EXPORT_DELAY_MS = 400
const IDLE_BUCKETS = ['all', '60_89', '90_179', '180_plus']
const IDLE_DEFAULT_LIMIT = 10
const IDLE_MAX_LIMIT = 50
const REPORT_NAMES = ['pnl', 'norm', 'stock']
const CONTENT_TYPES: Record<string, string> = {
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pdf: 'application/pdf',
}

interface Period {
  month: string
  asOf: string
}

/** Month and reference date from the query, with the checks of the contract: invalid -> 422, future -> 422. */
function readPeriod(url: URL): Period | Response {
  const scenario = getMockScenario()
  const asOf = url.searchParams.get('as_of') ?? (scenario === 'reportopen' ? OPEN_AS_OF : DEFAULT_AS_OF)
  if (!DATE_PATTERN.test(asOf)) return errorResponse(422, 'validation', 'Неверная дата.', { fields: { as_of: 'invalid' } })
  const month = url.searchParams.get('month')
  if (month !== null && !MONTH_PATTERN.test(month)) return errorResponse(422, 'validation', 'Неверный месяц.', { fields: { month: 'invalid' } })
  if (month !== null && month > monthOfDate(asOf)) return errorResponse(422, 'validation', 'Месяц в будущем.', { fields: { month: 'in_future' } })
  return { month: month ?? lastClosedMonth(asOf), asOf }
}

async function reportGuard(request: Request): Promise<Response | null> {
  const blocked = await guard(request)
  if (blocked) return blocked
  if (getMockScenario() === 'error') return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
  return null
}

function idleAnswer(url: URL): Response | StockIdlePage {
  const bucket = url.searchParams.get('bucket') ?? 'all'
  if (!IDLE_BUCKETS.includes(bucket)) return errorResponse(422, 'validation', 'Неверный интервал.', { fields: { bucket: 'invalid' } })
  const limitText = url.searchParams.get('limit')
  const limit = limitText === null ? IDLE_DEFAULT_LIMIT : Number(limitText)
  if (!Number.isInteger(limit) || limit < 1 || limit > IDLE_MAX_LIMIT) return errorResponse(422, 'validation', 'Неверный размер страницы.', { fields: { limit: 'invalid' } })
  const cursorText = url.searchParams.get('cursor')
  const offset = cursorText === null ? 0 : Number(cursorText)
  if (!Number.isInteger(offset) || offset < 0) return errorResponse(422, 'validation', 'Неверная страница.', { fields: { cursor: 'invalid' } })
  const nothing = ['reportempty', 'reportcalm'].includes(getMockScenario())
  const all: StockIdleItem[] = nothing ? [] : stockIdleExample.items.filter((item) => bucket === 'all' || item.bucket === bucket)
  const items = all.slice(offset, offset + limit)
  const next = offset + limit < all.length ? String(offset + limit) : null
  return {
    items,
    next_cursor: next,
    total: { ...stockIdleExample.total, value: all.length, breakdown: [] },
  }
}

export const reportsHandlers = [
  http.get('*/v1/reports/pnl', async ({ request }) => {
    const blocked = await reportGuard(request)
    if (blocked) return blocked
    const url = new URL(request.url)
    const view = url.searchParams.get('view') ?? 'clinic'
    if (view !== 'clinic' && view !== 'direction') return errorResponse(422, 'validation', 'Неверный режим.', { fields: { view: 'invalid' } })
    const period = readPeriod(url)
    if (period instanceof Response) return period
    return HttpResponse.json(buildPnl({ ...period, view, scenario: getMockScenario() }))
  }),
  http.get('*/v1/reports/norm', async ({ request }) => {
    const blocked = await reportGuard(request)
    if (blocked) return blocked
    const period = readPeriod(new URL(request.url))
    if (period instanceof Response) return period
    return HttpResponse.json(buildNorm({ ...period, scenario: getMockScenario() }))
  }),
  http.get('*/v1/reports/stock/idle', async ({ request }) => {
    const blocked = await reportGuard(request)
    if (blocked) return blocked
    const answer = idleAnswer(new URL(request.url))
    return answer instanceof Response ? answer : HttpResponse.json(answer)
  }),
  http.get('*/v1/reports/stock', async ({ request }) => {
    const blocked = await reportGuard(request)
    if (blocked) return blocked
    const url = new URL(request.url)
    const asOf = url.searchParams.get('as_of')
    if (asOf !== null && !DATE_PATTERN.test(asOf)) return errorResponse(422, 'validation', 'Неверная дата.', { fields: { as_of: 'invalid' } })
    return HttpResponse.json(buildStock({ scenario: getMockScenario(), asOf, month: url.searchParams.get('month') }))
  }),
  // The file is a stand-in with the right headers; the real one is built by the backend from the same figures.
  http.get('*/v1/reports/:name/export', async ({ request, params }) => {
    const blocked = await reportGuard(request)
    if (blocked) return blocked
    const name = String(params.name)
    if (!REPORT_NAMES.includes(name)) return errorResponse(404, 'not_found', 'Такого отчёта нет.')
    const url = new URL(request.url)
    const format = url.searchParams.get('format')
    if (format !== 'xlsx' && format !== 'pdf') {
      return errorResponse(422, 'validation', 'Неверный формат.', { fields: { format: format === null ? 'required' : 'invalid' } })
    }
    const scenario = getMockScenario()
    if (scenario === 'ratelimit') return errorResponse(429, 'rate_limited', 'Слишком много запросов.')
    if (scenario === 'exportfail') return HttpResponse.json({ status: 'not_implemented' }, { status: 501 })
    const period = readPeriod(url)
    if (period instanceof Response) return period
    await delay(EXPORT_DELAY_MS)
    const stamp = name === 'stock' ? monthOfDate(period.asOf) : period.month
    return new HttpResponse(`VetFinance mock export ${name} ${stamp}`, {
      headers: {
        'Content-Type': CONTENT_TYPES[format] ?? 'application/octet-stream',
        'Content-Disposition': `attachment; filename="vetfinance-${name}-${stamp}.${format}"`,
      },
    })
  }),
]
