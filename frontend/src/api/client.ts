import { getApiUrl } from '../lib/config'
import { ApiError, errorFromResponse, networkError } from './errors'

type TokenProvider = () => Promise<string | null>
type UnauthorizedHandler = () => void

let tokenProvider: TokenProvider = async () => null
let unauthorizedHandler: UnauthorizedHandler = () => undefined

export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider
}

export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler
}

function buildUrl(path: string): string {
  const base = getApiUrl() || window.location.origin
  return new URL(path, `${base}/`).toString()
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const token = await tokenProvider()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(buildUrl(path), { headers, signal })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw networkError(cause)
  }

  if (!response.ok) {
    const error = await errorFromResponse(response)
    if (error.kind === 'unauthorized') unauthorizedHandler()
    throw error
  }
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError('other', response.status, null, 'invalid JSON')
  }
}
