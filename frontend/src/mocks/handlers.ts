import { delay, http, HttpResponse } from 'msw'
import {
  accountListA,
  clinicA,
  dashboardA,
  dashboardNegative,
  dashboardNoAccounts,
  dashboardZero,
} from './fixtures'
import { getMockScenario, type MockScenario } from './scenario'

const SLOW_MS = 10_000

function errorResponse(status: number, code: string, message: string) {
  return HttpResponse.json({ error: { code, message, details: {} } }, { status })
}

/** Common checks: Bearer token and scenarios that break every request. Returns a response to stop, or null. */
async function guard(request: Request) {
  const scenario = getMockScenario()
  if (!request.headers.get('Authorization')?.startsWith('Bearer ') || scenario === 'expired') {
    return errorResponse(401, 'unauthorized', 'Нужен вход.')
  }
  if (scenario === 'noclinic') return errorResponse(403, 'forbidden', 'Почта не привязана к клинике.')
  if (scenario === 'network') return HttpResponse.error()
  if (scenario === 'slow') await delay(SLOW_MS)
  return null
}

function dashboardFor(scenario: MockScenario) {
  switch (scenario) {
    case 'empty':
      return dashboardNoAccounts
    case 'zero':
      return dashboardZero
    case 'negative':
      return dashboardNegative
    default:
      return dashboardA
  }
}

export const handlers = [
  http.get('*/v1/clinic', async ({ request }) => (await guard(request)) ?? HttpResponse.json(clinicA)),
  http.get('*/v1/accounts', async ({ request }) => (await guard(request)) ?? HttpResponse.json(accountListA)),
  http.get('*/v1/dashboard', async ({ request }) => {
    const blocked = await guard(request)
    if (blocked) return blocked
    const scenario = getMockScenario()
    if (scenario === 'error') return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
    return HttpResponse.json(dashboardFor(scenario))
  }),
]
