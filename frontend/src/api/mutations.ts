import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client'
import { invalidateAfterOperationChange, queryKeys } from './queries'
import type {
  AcquiringDay,
  Connection,
  CreateTransactionBody,
  ResolveDuplicateResult,
  RulePreview,
  SaveVetmanagerBody,
  SyncRun,
  Transaction,
  TransactionUpdateResult,
} from './types'

export interface UpdateCategoryVariables {
  id: string
  categoryId: string
  createRule: boolean
}

export function useUpdateCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, categoryId, createRule }: UpdateCategoryVariables) =>
      apiPatch<TransactionUpdateResult>(`/v1/transactions/${encodeURIComponent(id)}`, {
        category_id: categoryId,
        create_rule: createRule,
      }),
    onSuccess: () => invalidateAfterOperationChange(queryClient),
  })
}

export function useCreateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateTransactionBody) => apiPost<Transaction>('/v1/transactions', body),
    onSuccess: () => invalidateAfterOperationChange(queryClient),
  })
}

export type DuplicateDecision = { keepId: string } | { keepBoth: true }

export function useResolveDuplicate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: DuplicateDecision }) =>
      apiPost<ResolveDuplicateResult>(
        `/v1/transactions/${encodeURIComponent(id)}/resolve-duplicate`,
        'keepBoth' in decision ? { keep_both: true } : { keep_id: decision.keepId },
      ),
    onSuccess: () => invalidateAfterOperationChange(queryClient),
  })
}

export function useDeleteRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/v1/category-rules/${encodeURIComponent(id)}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.categoryRules }),
  })
}

export function fetchRulePreview(transactionId: string, categoryId: string, signal?: AbortSignal): Promise<RulePreview> {
  const params = new URLSearchParams({ category_id: categoryId })
  return apiGet<RulePreview>(`/v1/transactions/${encodeURIComponent(transactionId)}/rule-preview?${params.toString()}`, signal)
}

export function useSaveVetmanager() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SaveVetmanagerBody) => apiPut<Connection>('/v1/connections/vetmanager', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.connections }),
  })
}

export function useSyncConnection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiPost<{ run: SyncRun }>(`/v1/connections/${encodeURIComponent(id)}/sync`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.connections }),
  })
}

export function useReviewDay() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ date, note }: { date: string; note: string | null }) =>
      apiPost<AcquiringDay>(`/v1/acquiring/days/${date}/review`, { note }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.acquiring }),
  })
}
