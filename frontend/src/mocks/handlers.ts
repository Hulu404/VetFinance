import { http, HttpResponse } from 'msw'
import {
  accountListA,
  clinicA,
  dashboardA,
  dashboardEmptyMonth,
  dashboardFewData,
  dashboardNegative,
  dashboardNoAccounts,
  dashboardNoAdvice,
  dashboardNoRunway,
  dashboardStale,
  dashboardZero,
} from './fixtures'
import { acquiringHandlers } from './acquiringHandlers'
import { connectionHandlers } from './connectionHandlers'
import { errorResponse, guard } from './guard'
import { reportsHandlers } from './reportsHandlers'
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
    case 'emptymonth':
      return dashboardEmptyMonth
    case 'noadvice':
      return dashboardNoAdvice
    case 'fewdata':
      return dashboardFewData
    case 'norunway':
      return dashboardNoRunway
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
    // `?as_of=` is passed through as the reference date; the numbers stay those of the mock.
    const asOf = new URL(request.url).searchParams.get('as_of')
    if (asOf !== null && !/^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
      return errorResponse(422, 'validation', 'Неверная дата.', { fields: { as_of: 'invalid' } })
    }
    const dashboard = dashboardFor(scenario)
    return HttpResponse.json(asOf ? { ...dashboard, as_of: asOf } : dashboard)
  }),
  ...transactionHandlers,
  ...connectionHandlers,
  ...acquiringHandlers,
  ...reportsHandlers,
]
