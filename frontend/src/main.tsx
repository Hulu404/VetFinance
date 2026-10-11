import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './fonts'
import './styles/tokens.css'
import './styles/global.css'
import { shouldRetry } from './api/retry'
import { App } from './App'
import { AuthProvider } from './auth/AuthProvider'
import { isMockMode } from './lib/config'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: shouldRetry } },
})

async function bootstrap(): Promise<void> {
  if (isMockMode()) {
    const { startMockServer } = await import('./mocks/browser')
    await startMockServer()
  }
  const container = document.getElementById('root')
  if (!container) throw new Error('#root not found')
  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
}

void bootstrap()
