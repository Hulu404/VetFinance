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
  CalendarReport,
  CategoryList,
  CategoryRuleList,
  EfficiencyReport,
  EfficiencySettings,
  Clinic,
  ConnectionList,
  Dashboard,
  ObligationsReport,
  ServiceCost,
  ServiceFilter,
  ServiceList,
  ServiceRecipe,
  ServiceSort,
  SortOrder,
  StockItemList,
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
  calendar: ['calendar'] as const,
  obligations: ['obligations'] as const,
  services: ['services'] as const,
  serviceCost: ['service-cost'] as const,
  serviceRecipe: ['service-recipe'] as const,
  stockItems: ['stock-items'] as const,
  efficiency: ['efficiency'] as const,
  efficiencySettings: ['efficiency-settings'] as const,
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

/** The calendar of the next 22 days; `asOf` is passed through from the address (golden-data checks). */
export function useCalendar(asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.calendar, asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<CalendarReport>(reportQuery('/v1/calendar', { days: '22', as_of: asOf }), signal),
  })
}

export function useObligations(asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.obligations, asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<ObligationsReport>(reportQuery('/v1/obligations', { as_of: asOf }), signal),
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

/** After a payment, a deferral or the safe balance: the calendar, the dashboard (the `cash_gap` advice, the balance) and the clinic. */
export function invalidateAfterCalendarChange(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.calendar }),
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
    queryClient.invalidateQueries({ queryKey: queryKeys.clinic }),
  ])
}

/** After obligations change: they move the profit (reports), the calendar and the dashboard. */
export function invalidateAfterObligationChange(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.obligations }),
    queryClient.invalidateQueries({ queryKey: queryKeys.calendar }),
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
    queryClient.invalidateQueries({ queryKey: queryKeys.pnl }),
    queryClient.invalidateQueries({ queryKey: queryKeys.norm }),
  ])
}

export const SERVICES_PAGE_SIZE = 50
const STOCK_ITEMS_LIMIT = 200

export interface ServiceListParams {
  filter: ServiceFilter
  sort: ServiceSort
  order: SortOrder
  q: string
  asOf: string | null
}

/** The price list; the server filters, sorts and cuts it into pages. The previous rows stay while a new filter loads. */
export function useServices(params: ServiceListParams) {
  const { filter, sort, order, q, asOf } = params
  return useInfiniteQuery({
    queryKey: [...queryKeys.services, filter, sort, order, q, asOf ?? 'today'],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      apiGet<ServiceList>(
        reportQuery('/v1/services', { sort, order, filter, q: q || null, limit: String(SERVICES_PAGE_SIZE), cursor: pageParam, as_of: asOf }),
        signal,
      ),
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  })
}

export function useServiceCost(id: string | null, asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.serviceCost, id, asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<ServiceCost>(reportQuery(`/v1/services/${encodeURIComponent(id ?? '')}/cost`, { as_of: asOf }), signal),
    enabled: id !== null,
  })
}

export function useServiceRecipe(id: string | null, enabled = true) {
  return useQuery({
    queryKey: [...queryKeys.serviceRecipe, id],
    queryFn: ({ signal }) => apiGet<ServiceRecipe>(`/v1/services/${encodeURIComponent(id ?? '')}/recipe`, signal),
    enabled: id !== null && enabled,
    gcTime: 0,
  })
}

/** Warehouse items for the recipe form; the form filters them by the typed text. */
export function useStockItems(enabled = true) {
  return useQuery({
    queryKey: queryKeys.stockItems,
    queryFn: ({ signal }) => apiGet<StockItemList>(reportQuery('/v1/stock/items', { limit: String(STOCK_ITEMS_LIMIT) }), signal),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

/** Efficiency of a month; `month` null asks for the last closed one. */
export function useEfficiency(month: string | null, asOf: string | null) {
  return useQuery({
    queryKey: [...queryKeys.efficiency, month ?? 'default', asOf ?? 'today'],
    queryFn: ({ signal }) => apiGet<EfficiencyReport>(reportQuery('/v1/efficiency', { month, as_of: asOf }), signal),
    placeholderData: keepPreviousData,
  })
}

export function useEfficiencySettings(enabled = true) {
  return useQuery({
    queryKey: queryKeys.efficiencySettings,
    queryFn: ({ signal }) => apiGet<EfficiencySettings>('/v1/efficiency/settings', signal),
    enabled,
    gcTime: 0,
  })
}

/** After a service or a recipe changes: the list, the cards and the recipes. */
export function invalidateAfterServiceChange(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.services }),
    queryClient.invalidateQueries({ queryKey: queryKeys.serviceCost }),
    queryClient.invalidateQueries({ queryKey: queryKeys.serviceRecipe }),
  ])
}

/** The hours of doctors and the average length of a visit move the cost of an hour, which is a part of every price. */
export function invalidateAfterEfficiencyChange(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.efficiency }),
    queryClient.invalidateQueries({ queryKey: queryKeys.efficiencySettings }),
    invalidateAfterServiceChange(queryClient),
  ])
}
