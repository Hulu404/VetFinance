import type { ApiErrorBody } from './types'

export type ApiErrorKind = 'network' | 'unauthorized' | 'forbidden' | 'not_found' | 'server' | 'other'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number
  readonly code: string | null

  constructor(kind: ApiErrorKind, status: number, code: string | null, message: string) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const inner = (value as { error: unknown }).error
  return typeof inner === 'object' && inner !== null && typeof (inner as { code?: unknown }).code === 'string'
}

function kindFor(status: number, code: string | null): ApiErrorKind {
  if (status === 401 || code === 'unauthorized') return 'unauthorized'
  if (status === 403 || code === 'forbidden') return 'forbidden'
  if (status === 404 || code === 'not_found') return 'not_found'
  if (status >= 500 || code === 'sync_failed') return 'server'
  return 'other'
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  const code = isErrorBody(body) ? body.error.code : null
  const message = isErrorBody(body) ? body.error.message : response.statusText
  return new ApiError(kindFor(response.status, code), response.status, code, message)
}

export function networkError(cause: unknown): ApiError {
  return new ApiError('network', 0, null, cause instanceof Error ? cause.message : 'network error')
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}
