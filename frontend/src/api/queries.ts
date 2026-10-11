import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'
import type { Clinic, Dashboard } from './types'

export const queryKeys = {
  dashboard: ['dashboard'] as const,
  clinic: ['clinic'] as const,
}

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: ({ signal }) => apiGet<Dashboard>('/v1/dashboard', signal),
  })
}

export function useClinic() {
  return useQuery({
    queryKey: queryKeys.clinic,
    queryFn: ({ signal }) => apiGet<Clinic>('/v1/clinic', signal),
    staleTime: 5 * 60 * 1000,
  })
}
