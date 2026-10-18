import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from '../mocks/server'
import { setMockScenario } from '../mocks/scenario'
import { resetAcquiringState } from '../mocks/acquiringHandlers'
import { resetConnectionState } from '../mocks/connectionHandlers'
import { resetPlanningState } from '../mocks/planningStore'
import { resetPricing } from '../mocks/pricingStore'
import { resetTxStore } from '../mocks/txStore'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  setMockScenario('default')
  resetTxStore()
  resetConnectionState()
  resetAcquiringState()
  resetPlanningState()
  resetPricing()
  window.sessionStorage.clear()
})
afterAll(() => server.close())
