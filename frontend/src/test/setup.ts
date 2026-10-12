import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from '../mocks/server'
import { setMockScenario } from '../mocks/scenario'
import { resetAcquiringState } from '../mocks/acquiringHandlers'
import { resetConnectionState } from '../mocks/connectionHandlers'
import { resetTxStore } from '../mocks/txStore'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  setMockScenario('default')
  resetTxStore()
  resetConnectionState()
  resetAcquiringState()
  window.sessionStorage.clear()
})
afterAll(() => server.close())
