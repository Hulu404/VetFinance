import { ApiError } from './errors'

/** Retry once on network and server errors; auth and client errors will not change on retry. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.kind !== 'network' && error.kind !== 'server') return false
  return failureCount < 1
}
