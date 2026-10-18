// Dev switch for mock states: open the cabinet with ?mock=<name>. Remembered until the tab closes.
export type MockScenario =
  | 'default'
  | 'empty'
  | 'zero'
  | 'negative'
  | 'error'
  | 'network'
  | 'slow'
  | 'noclinic'
  | 'expired'
  // Stage 1
  | 'stale' // data_stale: true on the dashboard and connections
  | 'syncerror' // last Vetmanager run failed with invalid_key
  | 'txempty' // no operations at all
  | 'txerror' // every transactions endpoint answers 500
  | 'notconnected' // Vetmanager not connected, no bank statements yet
  | 'nostatement' // reconciliation: bank statement ends on 3 September
  | 'acqempty' // reconciliation: no card payments
  | 'acqerror' // reconciliation endpoints answer 500
  | 'ratelimit' // statement upload and sync answer 429
  // Stage 2 (dashboard)
  | 'emptymonth' // accounts exist, the month has no data yet
  | 'noadvice' // advice: []
  | 'fewdata' // 3 days of history: short chart, no week change, no advice
  | 'norunway' // runway_days is absent
  // Stage 3 (reports)
  | 'reportopen' // the reference date is 9 September: the month is open
  | 'reportloss' // P&L: a loss
  | 'reportzero' // P&L: expenses but no revenue, no shares
  | 'reportpartial' // all reasons of partial data
  | 'reportempty' // no data in any report
  | 'reportcalm' // stock: nothing expires, nothing idle
  | 'exportfail' // export answers 501 (backend step 1)
  // Stage 4 (planning)
  | 'cashgap' // the dashboard has the `cash_gap` advice made from the calendar alert
  | 'calnogap' // the calendar has no red days and no alerts
  | 'calpartialgap' // the suggestion only reduces the gap (closes_gap: false)
  | 'calnosuggest' // no move helps: suggestion is null
  | 'calpartial' // all partial reasons, 34 days of history
  | 'calempty' // no statements: the calendar cannot be built
  | 'calnosafe' // the safe balance is not set
  | 'calerror' // calendar endpoints answer 500
  | 'oblempty' // no obligations at all
  | 'oblerror' // obligations endpoints answer 500
  // Stage 5 (price list and efficiency)
  | 'priceempty' // no services at all
  | 'pricenorecipes' // every service is without a recipe
  | 'priceerror' // the list endpoints answer 500
  | 'pricecarderror' // the card endpoint answers 500
  | 'pricenohourcost' // the card of the cat castration lacks the cost of an hour
  | 'effward' // efficiency by doctors (no room schedule)
  | 'effnohours' // efficiency by doctors, no hours of reception set
  | 'effdoctornohours' // one doctor without hours
  | 'effnoexpenses' // no bank statement for the month
  | 'effempty' // no visits in the month
  | 'efferror' // efficiency endpoints answer 500

const SCENARIOS: readonly string[] = [
  'default',
  'empty',
  'zero',
  'negative',
  'error',
  'network',
  'slow',
  'noclinic',
  'expired',
  'stale',
  'syncerror',
  'txempty',
  'txerror',
  'notconnected',
  'nostatement',
  'acqempty',
  'acqerror',
  'ratelimit',
  'emptymonth',
  'noadvice',
  'fewdata',
  'norunway',
  'reportopen',
  'reportloss',
  'reportzero',
  'reportpartial',
  'reportempty',
  'reportcalm',
  'exportfail',
  'cashgap',
  'calnogap',
  'calpartialgap',
  'calnosuggest',
  'calpartial',
  'calempty',
  'calnosafe',
  'calerror',
  'oblempty',
  'oblerror',
  'priceempty',
  'pricenorecipes',
  'priceerror',
  'pricecarderror',
  'pricenohourcost',
  'effward',
  'effnohours',
  'effdoctornohours',
  'effnoexpenses',
  'effempty',
  'efferror',
]
const STORAGE_KEY = 'vf-mock-scenario'

let current: MockScenario = 'default'

export function setMockScenario(name: MockScenario): void {
  current = name
}

export function getMockScenario(): MockScenario {
  return current
}

export function initScenarioFromLocation(): void {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('mock')
    const name = fromUrl ?? window.sessionStorage.getItem(STORAGE_KEY)
    if (name && SCENARIOS.includes(name)) {
      current = name as MockScenario
      window.sessionStorage.setItem(STORAGE_KEY, name)
    }
  } catch {
    // storage unavailable: keep the default scenario
  }
}
