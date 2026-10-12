import { http, HttpResponse } from 'msw'
import {
  accountListA,
  clinicA,
  dashboardA,
  dashboardNegative,
  dashboardNoAccounts,
  dashboardStale,
  dashboardZero,
} from './fixtures'
import { acquiringHandlers } from './acquiringHandlers'
import { connectionHandlers } from './connectionHandlers'
import { errorResponse, guard } from './guard'
import { getMockScenario, type MockScenario } from './scenario'
import { transactionHandlers } from './transactionHandlers'

function dashboardFor(scenario: MockScenario) {
  switch (scenario) {
    case 'empty':
      return dashboardNoAccounts
    case 'zero':
      return dashboardZero
    case 'negative':
      return dashboardNegative
    case 'stale':
      return dashboardStale
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
  ...transactionHandlers,
  ...connectionHandlers,
  ...acquiringHandlers,
]
