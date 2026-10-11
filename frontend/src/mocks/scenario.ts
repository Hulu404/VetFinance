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
