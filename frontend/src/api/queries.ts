import { useRef } from 'react'
import { keepPreviousData, useInfiniteQuery, useQuery, type QueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { asOfFromSearch } from '../lib/asOf'
import { lastDayOfMonth } from '../lib/dates'
import { apiGet } from './client'
import type {
  AccountList,
  AcquiringDayDetails,
  AcquiringReconciliation,
  CategoryList,
  CategoryRuleList,
  Clinic,
  ConnectionList,
  Dashboard,
  NormReport,
  PnlReport,
  PnlView,
  StockIdleKey,
  StockIdlePage,
  StockReport,
  TransactionCounts,
  TransactionList,
  TransactionSummary,
  TxTab,
} from './types'

export const PAGE_SIZE = 50
/** Polling period of connections while a sync runs, and its limit (design/screens/connections.md). */
export const SYNC_POLL_MS = 3000
export const SYNC_POLL_LIMIT_MS = 10 * 60 * 1000

export const queryKeys = {
  dashboard: ['dashboard'] as const,
  clinic: ['clinic'] as const,
  accounts: ['accounts'] as const,
  categories: ['categories'] as const,
  categoryRules: ['category-rules'] as const,
  connections: ['connections'] as const,
  transactions: ['transactions'] as const,
  transactionList: (tab: TxTab, month: string) => ['transactions', 'list', tab, tab === 'all' ? month : 'all-months'] as const,
  transactionCounts: ['transactions', 'counts'] as const,
  transactionSummary: (month: string) => ['transactions', 'summary', month] as const,
  acquiring: ['acquiring'] as const,
  acquiringMonth: (month: string) => ['acquiring', month] as const,
  acquiringDay: (date: string) => ['acquiring', 'day', date] as const,
  pnl: ['pnl'] as const,
  norm: ['norm'] as const,
  stock: ['stock'] as const,
  stockIdle: ['stock-idle'] as const,
}

/** Shared by the dashboard and the header balance. `?as_of=` in the address is passed through (golden-data checks). */
export function useDashboard() {
  const asOf = asOfFromSearch(useLocation().search)
  return useQuery({
    queryKey: [...queryKeys.dashboard, asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<Dashboard>(asOf ? `/v1/dashboard?as_of=${asOf}` : '/v1/dashboard', signal),
  })
}

export function useClinic() {
  return useQuery({
    queryKey: queryKeys.clinic,
    queryFn: ({ signal }) => apiGet<Clinic>('/v1/clinic', signal),
    staleTime: 5 * 60 * 1000,
  })
}

export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: ({ signal }) => apiGet<AccountList>('/v1/accounts', signal),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCategories() {
  return useQuery({
    queryKey: queryKeys.categories,
    queryFn: ({ signal }) => apiGet<CategoryList>('/v1/categories', signal),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCategoryRules(enabled = true) {
  return useQuery({
    queryKey: queryKeys.categoryRules,
    queryFn: ({ signal }) => apiGet<CategoryRuleList>('/v1/category-rules', signal),
    enabled,
  })
}

export function useTransactionCounts() {
  return useQuery({
    queryKey: queryKeys.transactionCounts,
    queryFn: ({ signal }) => apiGet<TransactionCounts>('/v1/transactions/counts', signal),
  })
}

export function useTransactionSummary(month: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.transactionSummary(month),
    queryFn: ({ signal }) => apiGet<TransactionSummary>(`/v1/transactions/summary?month=${month}`, signal),
    enabled,
  })
}

/** "all" is limited to the month; "check" and "duplicates" cover all months (design/screens/transactions.md). */
export function useTransactionList(tab: TxTab, month: string) {
  return useInfiniteQuery({
    queryKey: queryKeys.transactionList(tab, month),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => {
      const params = new URLSearchParams({ tab, limit: String(PAGE_SIZE) })
      if (tab === 'all') {
        params.set('from', `${month}-01`)
        params.set('to', lastDayOfMonth(month))
      }
      if (pageParam) params.set('cursor', pageParam)
      return apiGet<TransactionList>(`/v1/transactions?${params.toString()}`, signal)
    },
    getNextPageParam: (last) => last.next_cursor,
  })
}

/** Connections; polls while any run is going (`pollWhileRunning`), for at most SYNC_POLL_LIMIT_MS. */
export function useConnections(options: { pollWhileRunning?: boolean } = {}) {
  const pollStartedAt = useRef<number | null>(null)
  return useQuery({
    queryKey: queryKeys.connections,
    queryFn: ({ signal }) => apiGet<ConnectionList>('/v1/connections', signal),
    refetchInterval: (query) => {
      if (!options.pollWhileRunning) return false
      const running = (query.state.data?.items ?? []).some((item) => item.last_run?.status === 'running')
      if (!running) {
        pollStartedAt.current = null
        return false
      }
      pollStartedAt.current ??= Date.now()
      return Date.now() - pollStartedAt.current > SYNC_POLL_LIMIT_MS ? false : SYNC_POLL_MS
    },
  })
}

export function useAcquiring(month: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.acquiringMonth(month),
    queryFn: ({ signal }) => apiGet<AcquiringReconciliation>(`/v1/acquiring/reconciliation?month=${month}`, signal),
    enabled,
  })
}

export function useAcquiringDay(date: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.acquiringDay(date),
    queryFn: ({ signal }) => apiGet<AcquiringDayDetails>(`/v1/acquiring/days/${date}`, signal),
    enabled,
  })
}

function reportQuery(path: string, params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [name, value] of Object.entries(params)) {
    if (value) search.set(name, value)
  }
  const text = search.toString()
  return text ? `${path}?${text}` : path
}

/** P&L; `month` null asks for the last closed month. The previous answer stays on screen while a new month loads. */
export function usePnl(month: string | null, view: PnlView, asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.pnl, month ?? 'default', view, asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<PnlReport>(reportQuery('/v1/reports/pnl', { month, view, as_of: asOf }), signal),
    placeholderData: keepPreviousData,
  })
}

export function useNorm(month: string | null, asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.norm, month ?? 'default', asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<NormReport>(reportQuery('/v1/reports/norm', { month, as_of: asOf }), signal),
    placeholderData: keepPreviousData,
  })
}

export function useStock(asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.stock, asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<StockReport>(reportQuery('/v1/reports/stock', { as_of: asOf }), signal),
  })
}

/** One interval of "Товары без движения", ten rows per page. */
export function useStockIdle(bucket: StockIdleKey, asOf: string | null) {
  return useInfiniteQuery({
    queryKey: [...queryKeys.stockIdle, bucket, asOf ?? 'today'],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      apiGet<StockIdlePage>(reportQuery('/v1/reports/stock/idle', { bucket, cursor: pageParam, as_of: asOf }), signal),
    getNextPageParam: (last) => last.next_cursor,
  })
}

/** After anything that changes operations: lists, counters, month totals, balance in the header, reconciliation. */
export function invalidateAfterOperationChange(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.transactions }),
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
    queryClient.invalidateQueries({ queryKey: queryKeys.acquiring }),
    queryClient.invalidateQueries({ queryKey: queryKeys.pnl }),
    queryClient.invalidateQueries({ queryKey: queryKeys.norm }),
    queryClient.invalidateQueries({ queryKey: queryKeys.categoryRules }),
    queryClient.invalidateQueries({ queryKey: queryKeys.connections }),
  ])
}
