import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
import { initScenarioFromLocation } from './scenario'

export async function startMockServer(): Promise<void> {
  initScenarioFromLocation()
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    quiet: true,
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
  })
}
