import type { ApiErrorBody } from './types'

export type ApiErrorKind =
  | 'network'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'validation'
  | 'conflict'
  | 'rate_limited'
  | 'server'
  | 'other'

export type ApiErrorDetails = Record<string, unknown>

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number
  readonly code: string | null
  readonly details: ApiErrorDetails

  constructor(kind: ApiErrorKind, status: number, code: string | null, message: string, details: ApiErrorDetails = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
    this.details = details
  }

  /** Field problems of a `validation` error: { amount: "must_be_positive" }. */
  get fields(): Record<string, string> {
    const raw = this.details.fields
    if (typeof raw !== 'object' || raw === null) return {}
    const result: Record<string, string> = {}
    for (const [key, value] of Object.entries(raw)) {
      if (typeof value === 'string') result[key] = value
    }
    return result
  }

  /** Machine reason of a `validation` error (`details.reason`), e.g. "unsupported_format". */
  get reason(): string | null {
    return typeof this.details.reason === 'string' ? this.details.reason : null
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
  if (status === 429) return 'rate_limited'
  if (status === 409 || code === 'conflict') return 'conflict'
  if (status === 422 || code === 'validation') return 'validation'
  if (status >= 500 || code === 'sync_failed') return 'server'
  return 'other'
}

export function errorFromParts(status: number, body: unknown, statusText = ''): ApiError {
  const code = isErrorBody(body) ? body.error.code : null
  const message = isErrorBody(body) ? body.error.message : statusText
  const details = isErrorBody(body) && body.error.details ? body.error.details : {}
  return new ApiError(kindFor(status, code), status, code, message, details)
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  return errorFromParts(response.status, body, response.statusText)
}

export function networkError(cause: unknown): ApiError {
  return new ApiError('network', 0, null, cause instanceof Error ? cause.message : 'network error')
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}
