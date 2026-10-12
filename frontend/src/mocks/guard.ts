import { delay, HttpResponse } from 'msw'
import { getMockScenario } from './scenario'

const SLOW_MS = 10_000

export function errorResponse(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
  return HttpResponse.json({ error: { code, message, details } }, { status })
}

/** Common checks: Bearer token and scenarios that break every request. Returns a response to stop, or null. */
export async function guard(request: Request) {
  const scenario = getMockScenario()
  if (!request.headers.get('Authorization')?.startsWith('Bearer ') || scenario === 'expired') {
    return errorResponse(401, 'unauthorized', 'Нужен вход.')
  }
  if (scenario === 'noclinic') return errorResponse(403, 'forbidden', 'Почта не привязана к клинике.')
  if (scenario === 'network') return HttpResponse.error()
  if (scenario === 'slow') await delay(SLOW_MS)
  return null
}
