import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './client'
import { invalidateAfterCalendarChange, invalidateAfterEfficiencyChange, invalidateAfterServiceChange, invalidateAfterObligationChange, invalidateAfterOperationChange, queryKeys } from './queries'
import type {
  AcquiringDay,
  Clinic,
  ClinicPatch,
  Connection,
  Counterparty,
  EfficiencySettings,
  EfficiencySettingsBody,
  Equipment,
  Loan,
  ManualPayment,
  ManualPaymentBody,
  ObligationBody,
  ObligationPatchBody,
  RecipeBody,
  ServiceBody,
  ServiceItem,
  ServicePatchBody,
  ServiceRecipe,
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

export function useCreatePayment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ManualPaymentBody) => apiPost<ManualPayment>('/v1/calendar/payments', body),
    onSuccess: () => invalidateAfterCalendarChange(queryClient),
  })
}

export function useDeletePayment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/v1/calendar/payments/${encodeURIComponent(id)}`),
    onSuccess: () => invalidateAfterCalendarChange(queryClient),
  })
}

export function useSetDeferral() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, days }: { id: string; days: number }) =>
      apiPatch<Counterparty>(`/v1/counterparties/${encodeURIComponent(id)}`, { max_deferral_days: days }),
    onSuccess: () => invalidateAfterCalendarChange(queryClient),
  })
}

export function usePatchClinic() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ClinicPatch) => apiPatch<Clinic>('/v1/clinic', body),
    onSuccess: () => invalidateAfterCalendarChange(queryClient),
  })
}

export function useCreateObligation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ObligationBody) => apiPost<Loan | Equipment>('/v1/obligations', body),
    onSuccess: () => invalidateAfterObligationChange(queryClient),
  })
}

export function usePatchObligation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ObligationPatchBody }) =>
      apiPatch<Loan | Equipment>(`/v1/obligations/${encodeURIComponent(id)}`, body),
    onSuccess: () => invalidateAfterObligationChange(queryClient),
  })
}

/** "Delete" closes the obligation from the current month; the row stays in the list (decision of the owner, 2026-10-16). */
export function useCloseObligation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/v1/obligations/${encodeURIComponent(id)}`),
    onSuccess: () => invalidateAfterObligationChange(queryClient),
  })
}

export function useCreateService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ServiceBody) => apiPost<ServiceItem>('/v1/services', body),
    onSuccess: () => invalidateAfterServiceChange(queryClient),
  })
}

export function usePatchService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ServicePatchBody }) => apiPatch<void>(`/v1/services/${encodeURIComponent(id)}`, body),
    onSuccess: () => invalidateAfterServiceChange(queryClient),
  })
}

export function useDeleteService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/v1/services/${encodeURIComponent(id)}`),
    onSuccess: () => invalidateAfterServiceChange(queryClient),
  })
}

export function useSaveRecipe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RecipeBody }) => apiPut<ServiceRecipe>(`/v1/services/${encodeURIComponent(id)}/recipe`, body),
    onSuccess: () => invalidateAfterServiceChange(queryClient),
  })
}

export function useSaveEfficiencySettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EfficiencySettingsBody) => apiPut<EfficiencySettings>('/v1/efficiency/settings', body),
    onSuccess: () => invalidateAfterEfficiencyChange(queryClient),
  })
}
