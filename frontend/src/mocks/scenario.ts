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
