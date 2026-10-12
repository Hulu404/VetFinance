import { getApiUrl } from '../lib/config'
import { ApiError, errorFromParts, errorFromResponse, networkError } from './errors'

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

async function authHeaders(): Promise<Record<string, string>> {
  const token = await tokenProvider()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function request<T>(method: string, path: string, init: { body?: BodyInit; json?: unknown; signal?: AbortSignal }): Promise<T> {
  const headers = await authHeaders()
  let body = init.body
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(init.json)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path), { method, headers, body, signal: init.signal })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw networkError(cause)
  }

  if (!response.ok) {
    const error = await errorFromResponse(response)
    if (error.kind === 'unauthorized') unauthorizedHandler()
    throw error
  }
  if (response.status === 204) return undefined as T
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError('other', response.status, null, 'invalid JSON')
  }
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>('GET', path, { signal })
}

export function apiPost<T>(path: string, json?: unknown): Promise<T> {
  return request<T>('POST', path, { json: json ?? {} })
}

export function apiPatch<T>(path: string, json: unknown): Promise<T> {
  return request<T>('PATCH', path, { json })
}

export function apiPut<T>(path: string, json: unknown): Promise<T> {
  return request<T>('PUT', path, { json })
}

export function apiDelete(path: string): Promise<void> {
  return request<void>('DELETE', path, {})
}

export interface UploadHandle<T> {
  promise: Promise<T>
  abort: () => void
}

/**
 * multipart/form-data upload with progress. XMLHttpRequest is used because fetch cannot report upload progress.
 * `onProgress` gets a whole percent (0-100) while bytes go out; `onSent` fires when the body is fully sent.
 */
export function apiUpload<T>(
  path: string,
  form: FormData,
  callbacks: { onProgress?: (percent: number) => void; onSent?: () => void } = {},
): UploadHandle<T> {
  const xhr = new XMLHttpRequest()
  let aborted = false
  const promise = (async () => {
    const headers = await authHeaders()
    return new Promise<T>((resolve, reject) => {
      if (aborted) {
        reject(new DOMException('Aborted', 'AbortError'))
        return
      }
      xhr.open('POST', buildUrl(path))
      for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value)
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          callbacks.onProgress?.(Math.min(100, Math.floor((event.loaded / event.total) * 100)))
        }
      }
      xhr.upload.onload = () => callbacks.onSent?.()
      xhr.onerror = () => reject(networkError(new Error('upload failed')))
      xhr.ontimeout = () => reject(networkError(new Error('upload timed out')))
      xhr.onabort = () => reject(new DOMException('Aborted', 'AbortError'))
      xhr.onload = () => {
        let parsed: unknown = null
        try {
          parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null
        } catch {
          parsed = null
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          if (parsed === null) reject(new ApiError('other', xhr.status, null, 'invalid JSON'))
          else resolve(parsed as T)
          return
        }
        const error = errorFromParts(xhr.status, parsed, xhr.statusText)
        if (error.kind === 'unauthorized') unauthorizedHandler()
        reject(error)
      }
      xhr.send(form)
    })
  })()
  return {
    promise,
    abort: () => {
      aborted = true
      xhr.abort()
    },
  }
}
