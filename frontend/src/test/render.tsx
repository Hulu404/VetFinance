import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { setTokenProvider } from '../api/client'
import { AuthProvider } from '../auth/AuthProvider'
import { createMockAuth } from '../auth/mockAuth'
import { ToastProvider } from '../components/Toast'

export function createTestQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
}

interface RenderOptions {
  /** Mount the toast zone (its alert region would confuse queries by role "alert" in other tests). */
  toasts?: boolean
}

function withToasts(children: ReactNode, toasts: boolean): ReactNode {
  return toasts ? <ToastProvider>{children}</ToastProvider> : children
}

/** Queries only (no auth): the API client gets a fixed token. */
export function renderWithQuery(ui: ReactElement, options: RenderOptions & { path?: string } = {}) {
  setTokenProvider(async () => 'test-token')
  const queryClient = createTestQueryClient()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[options.path ?? '/']}>{withToasts(ui, options.toasts ?? false)}</MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}

/** Whole app logic with the mock auth client. */
export function renderWithAuth(ui: ReactElement, initialPath = '/', options: RenderOptions = {}) {
  const queryClient = createTestQueryClient()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider client={createMockAuth()}>{withToasts(ui, options.toasts ?? false)}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}
