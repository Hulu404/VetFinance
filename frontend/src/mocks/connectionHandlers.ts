import { http, HttpResponse } from 'msw'
import type { Connection, SyncRun } from '../api/types'
import { countFigure } from './figures'
import { errorResponse, guard } from './guard'
import { getMockScenario } from './scenario'

const SYNC_DURATION_MS = 2500

function run(id: string, status: SyncRun['status'], startedAt: string, loaded: number | null, errorCode: SyncRun['error_code'] = null): SyncRun {
  return {
    id,
    status,
    started_at: startedAt,
    finished_at: status === 'running' ? null : startedAt.replace('04:12:00', '04:13:30'),
    error_code: errorCode,
    counts:
      loaded === null
        ? null
        : countFigure(
            loaded,
            [
              ['Новых операций', loaded],
              ['Обновлено', 0],
              ['Пропущено как дубли', 0],
            ],
            ['vetmanager'],
            'Операции, которые Ветменеджер отдал за этот запуск.',
          ),
  }
}

interface State {
  vetmanager: Connection
  bankLastStatementTo: string | null
  /** In the "notconnected" scenario the clinic is disconnected until the form is saved. */
  userConnected: boolean
  syncTimer: ReturnType<typeof setTimeout> | null
}

function initialVetmanager(): Connection {
  const last = run('run-5', 'success', '2026-09-09T04:12:00+03:00', 24)
  return {
    id: 'vetmanager',
    type: 'vetmanager',
    connected: true,
    address: 'aibolit.vetmanager.ru',
    key_hint: '4a7f',
    schedule: { kind: 'nightly', time: '04:00' },
    data_stale: false,
    last_success_at: '2026-09-09T04:12:00+03:00',
    last_run: last,
    runs: [
      last,
      run('run-4', 'partial', '2026-09-08T04:12:00+03:00', 11),
      run('run-3', 'failed', '2026-09-07T04:12:00+03:00', null, 'unreachable'),
      run('run-2', 'success', '2026-09-06T04:12:00+03:00', 0),
      run('run-1', 'success', '2026-09-05T04:12:00+03:00', 31),
    ],
    bank: null,
  }
}

let state: State = freshState()

function freshState(): State {
  return { vetmanager: initialVetmanager(), bankLastStatementTo: '2026-09-09', userConnected: false, syncTimer: null }
}

export function resetConnectionState(): void {
  if (state.syncTimer) clearTimeout(state.syncTimer)
  state = freshState()
}

function bankConnection(): Connection {
  const scenario = getMockScenario()
  const never = scenario === 'notconnected'
  const stale = scenario === 'stale'
  const to = never ? null : stale ? '2026-08-28' : state.bankLastStatementTo
  return {
    id: 'bank',
    type: 'bank',
    connected: !never,
    address: null,
    key_hint: null,
    schedule: null,
    data_stale: stale,
    last_success_at: null,
    last_run: null,
    runs: [],
    bank: {
      accounts: [
        { account: { id: 'A-bank', name: 'Расчётный счёт · 0101' }, last_statement_to: to },
        { account: { id: 'A-bank2', name: 'Резервный счёт · 0102' }, last_statement_to: never ? null : '2026-08-28' },
      ],
    },
  }
}

function vetmanagerFor(): Connection {
  const scenario = getMockScenario()
  const base = state.vetmanager
  if (scenario === 'notconnected' && !state.userConnected) {
    return { ...base, connected: false, address: null, key_hint: null, schedule: null, last_success_at: null, last_run: null, runs: [] }
  }
  if (scenario === 'stale') {
    return { ...base, data_stale: true, last_success_at: '2026-09-08T04:12:00+03:00' }
  }
  if (scenario === 'syncerror' && base.last_run?.status !== 'running') {
    const failed = run('run-6', 'failed', '2026-09-09T04:12:00+03:00', null, 'invalid_key')
    return { ...base, last_run: failed, runs: [failed, ...base.runs.slice(0, 4)], last_success_at: '2026-09-08T04:12:00+03:00' }
  }
  return base
}

function startSync(): SyncRun {
  const started = run('run-new', 'running', '2026-09-09T12:00:00+03:00', null)
  state.vetmanager = { ...state.vetmanager, last_run: started, runs: [started, ...state.vetmanager.runs.slice(0, 4)] }
  if (state.syncTimer) clearTimeout(state.syncTimer)
  state.syncTimer = setTimeout(() => {
    const finished = run('run-new', 'success', '2026-09-09T12:00:00+03:00', 7)
    const done = { ...finished, finished_at: '2026-09-09T12:00:40+03:00' }
    state.vetmanager = {
      ...state.vetmanager,
      last_run: done,
      last_success_at: done.finished_at,
      data_stale: false,
      runs: [done, ...state.vetmanager.runs.slice(1)],
    }
    state.syncTimer = null
  }, SYNC_DURATION_MS)
  return started
}

type SaveBody = { address?: string; key?: string }

async function saveVetmanager(request: Request) {
  const body = (await request.json()) as SaveBody
  const address = (body.address ?? '').trim()
  if (!address) return errorResponse(422, 'validation', 'Введите адрес.', { fields: { address: 'required' } })
  if (address.includes('bad')) return errorResponse(422, 'validation', 'Адрес недоступен.', { fields: { address: 'unreachable' } })
  const current = state.vetmanager
  const isNew = getMockScenario() === 'notconnected' && !state.userConnected
  if (isNew && !body.key) return errorResponse(422, 'validation', 'Нужен ключ.', { fields: { key: 'required' } })
  if (body.key && body.key.toLowerCase().includes('wrong')) {
    return errorResponse(422, 'validation', 'Ключ не принят.', { fields: { key: 'invalid' } })
  }
  const hint = body.key ? body.key.slice(-4) : current.key_hint
  state.vetmanager = {
    ...current,
    connected: true,
    address,
    key_hint: hint,
    schedule: { kind: 'nightly', time: '04:00' },
  }
  state.userConnected = true
  if (isNew) {
    state.vetmanager = { ...state.vetmanager, last_run: null, runs: [], last_success_at: null }
    startSync()
  }
  return HttpResponse.json(state.vetmanager)
}

export const connectionHandlers = [
  http.get('*/v1/connections', async ({ request }) => {
    const blocked = await guard(request)
    if (blocked) return blocked
    if (getMockScenario() === 'txerror') return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
    return HttpResponse.json({ items: [vetmanagerFor(), bankConnection()] })
  }),
  http.put('*/v1/connections/vetmanager', async ({ request }) => (await guard(request)) ?? saveVetmanager(request)),
  http.post('*/v1/connections/:id/sync', async ({ request, params }) => {
    const blocked = await guard(request)
    if (blocked) return blocked
    if (params.id !== 'vetmanager') return errorResponse(404, 'not_found', 'Подключение не найдено.')
    if (getMockScenario() === 'ratelimit') return errorResponse(429, 'validation', 'Слишком часто.')
    if (state.vetmanager.last_run?.status === 'running') return errorResponse(409, 'conflict', 'Синхронизация уже идёт.')
    return HttpResponse.json({ run: startSync() }, { status: 202 })
  }),
]
