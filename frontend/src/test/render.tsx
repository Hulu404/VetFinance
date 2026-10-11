import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { setTokenProvider } from '../api/client'
import { AuthProvider } from '../auth/AuthProvider'
import { createMockAuth } from '../auth/mockAuth'

export function createTestQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
}

/** Queries only (no auth): the API client gets a fixed token. */
export function renderWithQuery(ui: ReactElement) {
  setTokenProvider(async () => 'test-token')
  const queryClient = createTestQueryClient()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}

/** Whole app logic with the mock auth client. */
export function renderWithAuth(ui: ReactElement, initialPath = '/') {
  const queryClient = createTestQueryClient()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider client={createMockAuth()}>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}
