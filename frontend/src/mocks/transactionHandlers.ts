import { delay, http, HttpResponse } from 'msw'
import type { CreatedRule, ImportResult, TransactionSummary } from '../api/types'
import { rubFigure } from './figures'
import { errorResponse, guard } from './guard'
import { getMockScenario } from './scenario'
import {
  ACCOUNT_REFS,
  CATEGORIES,
  categoryRef,
  counts,
  getStore,
  newId,
  ruleDto,
  ruleMatches,
  toDto,
  type StoredTx,
} from './txStore'

const TODAY = '2026-09-09'
const OPENING_DATE = '2026-08-01'
const MAX_KOPECKS = 10_000_000_000

const summarySeptember: TransactionSummary = {
  income: rubFigure(
    29640000,
    [
      ['Выручка (эквайринг)', 26450000],
      ['Выручка', 3190000],
    ],
    ['bank', 'vetmanager'],
    'Доходы за сентябрь без переводов между счетами и без дублей.',
  ),
  expense: rubFigure(
    28100000,
    [
      ['Аренда', 8500000],
      ['Препараты', 12130000],
      ['Налоги и взносы', 3200000],
      ['Без статьи', 4270000],
    ],
    ['bank', 'manual'],
    'Расходы за сентябрь без переводов между счетами и без дублей. Операции без статьи входят в строку «Без статьи».',
  ),
  balance: rubFigure(
    1540000,
    [
      ['Доходы', 29640000],
      ['Расходы', -28100000],
    ],
    ['calc'],
    'Сальдо месяца: доходы минус расходы. Переводы между своими счетами не входят. Это не остаток на счетах.',
  ),
}

const summaryEmpty: TransactionSummary = {
  income: rubFigure(0, [], ['bank'], 'За этот месяц доходов нет.'),
  expense: rubFigure(0, [], ['bank'], 'За этот месяц расходов нет.'),
  balance: rubFigure(0, [], ['calc'], 'Сальдо месяца: доходы минус расходы. Переводы между своими счетами не входят.'),
}

async function checked(request: Request) {
  const blocked = await guard(request)
  if (blocked) return blocked
  if (getMockScenario() === 'txerror') return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
  return null
}

function listTransactions(url: URL) {
  const tab = url.searchParams.get('tab') ?? 'all'
  const from = url.searchParams.get('from')
  const to = url.searchParams.get('to')
  const limit = Number(url.searchParams.get('limit') ?? 50)
  const offset = Number(url.searchParams.get('cursor') ?? 0)
  if (!['all', 'check', 'duplicates'].includes(tab) || !Number.isFinite(limit) || limit < 1) {
    return errorResponse(422, 'validation', 'Неверные параметры запроса.')
  }
  const scenario = getMockScenario()
  let rows = scenario === 'txempty' ? [] : getStore().transactions
  if (tab === 'check') rows = rows.filter((t) => t.status === 'check')
  if (tab === 'duplicates') rows = rows.filter((t) => t.duplicateState === 'pending')
  if (tab === 'all' && from && to) rows = rows.filter((t) => t.date >= from && t.date <= to)
  const sorted = [...rows].sort((a, b) => (a.date === b.date ? a.id.localeCompare(b.id) : b.date.localeCompare(a.date)))
  const page = sorted.slice(offset, offset + limit)
  const next = offset + limit < sorted.length ? String(offset + limit) : null
  return HttpResponse.json({ items: page.map((t) => toDto(t)), next_cursor: next })
}

async function patchTransaction(request: Request, id: string) {
  const body = (await request.json()) as { category_id?: string; create_rule?: boolean }
  const store = getStore()
  const target = store.transactions.find((t) => t.id === id)
  if (!target) return errorResponse(404, 'not_found', 'Операция не найдена.')
  if (!body.category_id || !categoryRef(body.category_id)) return errorResponse(422, 'validation', 'Статья не найдена.')
  if (getMockScenario() === 'txerror') return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')

  let rule: CreatedRule | null = null
  const categoryId = body.category_id
  const counterparty = target.counterparty
  if (body.create_rule && counterparty) {
    const affected = ruleMatches(counterparty, target.id)
    const created = {
      id: newId('r'),
      match: 'inn' as const,
      direction: target.amount < 0 ? ('out' as const) : ('in' as const),
      matchText: counterparty,
      categoryId,
      appliedThisMonth: affected.length,
      appliedBefore: 0,
      createdAt: TODAY,
    }
    store.rules.unshift(created)
    for (const other of affected) {
      other.categoryId = categoryId
      other.status = 'ok'
    }
    rule = {
      id: created.id,
      match_text: counterparty,
      category: categoryRef(categoryId) ?? { id: categoryId, name: categoryId },
      applied_count: affected.length,
    }
  }
  target.categoryId = categoryId
  target.status = 'ok'
  target.byHand = !rule
  return HttpResponse.json({ ...toDto(target), rule })
}

type CreateBody = {
  kind?: string
  account_id?: string
  category_id?: string | null
  date?: string
  amount?: number
  comment?: string | null
}

function validateCreate(body: CreateBody): Record<string, string> {
  const fields: Record<string, string> = {}
  if (!body.account_id) fields.account_id = 'required'
  else if (!ACCOUNT_REFS[body.account_id]) fields.account_id = 'required'
  if (typeof body.amount !== 'number') fields.amount = 'required'
  else if (body.amount <= 0) fields.amount = 'must_be_positive'
  else if (body.amount > MAX_KOPECKS) fields.amount = 'too_large'
  if (!body.date) fields.date = 'required'
  else if (body.date > TODAY) fields.date = 'in_future'
  else if (body.date < OPENING_DATE) fields.date = 'before_opening'
  if (body.comment && body.comment.length > 200) fields.comment = 'too_long'
  return fields
}

async function createTransaction(request: Request) {
  const body = (await request.json()) as CreateBody
  const fields = validateCreate(body)
  if (Object.keys(fields).length > 0) {
    return errorResponse(422, 'validation', 'Проверьте поля.', { fields })
  }
  const store = getStore()
  const kind = body.kind === 'in' ? 'in' : 'out'
  const amount = kind === 'in' ? (body.amount ?? 0) : -(body.amount ?? 0)
  const accountId = (body.account_id ?? 'A-bank') as keyof typeof ACCOUNT_REFS
  const similar = store.transactions.find(
    (t) => t.accountId === accountId && t.amount === amount && t.source !== 'manual' && t.duplicateState !== 'pending',
  )
  const created: StoredTx = {
    id: newId('t'),
    date: body.date ?? TODAY,
    description: body.comment?.trim() || (kind === 'in' ? 'Доход, внесён вручную' : 'Расход, внесён вручную'),
    categoryId: body.category_id ?? null,
    accountId,
    source: 'manual',
    amount,
    kind,
    status: similar ? 'duplicate' : body.category_id ? 'ok' : 'check',
    counterparty: null,
    byHand: Boolean(body.category_id),
    duplicateOfId: similar?.id ?? null,
    duplicateReason: similar ? 'одинаковая сумма, близкие даты, разные источники' : null,
    duplicateState: similar ? 'pending' : null,
  }
  store.transactions.push(created)
  return HttpResponse.json(toDto(created), { status: 201 })
}

async function resolveDuplicate(request: Request, id: string) {
  const body = (await request.json()) as { keep_id?: string; keep_both?: boolean }
  const store = getStore()
  const flagged = store.transactions.find((t) => t.id === id)
  if (!flagged || flagged.duplicateState !== 'pending') return errorResponse(404, 'not_found', 'Пара не найдена.')
  const original = store.transactions.find((t) => t.id === flagged.duplicateOfId)
  if (body.keep_both) {
    flagged.status = flagged.categoryId ? 'ok' : 'check'
    flagged.duplicateState = null
    flagged.duplicateOfId = null
    return HttpResponse.json({ kept: [toDto(flagged), ...(original ? [toDto(original)] : [])], duplicates: [] })
  }
  if (body.keep_id === flagged.id && original) {
    original.status = 'duplicate'
    original.duplicateState = 'confirmed'
    original.duplicateOfId = flagged.id
    flagged.status = flagged.categoryId ? 'ok' : 'check'
    flagged.duplicateState = null
    flagged.duplicateOfId = null
    return HttpResponse.json({ kept: [toDto(flagged)], duplicates: [toDto(original)] })
  }
  if (body.keep_id !== flagged.id && body.keep_id !== original?.id) {
    return errorResponse(422, 'validation', 'Операция не из пары.', { fields: { keep_id: 'invalid' } })
  }
  flagged.duplicateState = 'confirmed'
  return HttpResponse.json({ kept: original ? [toDto(original)] : [], duplicates: [toDto(flagged)] })
}

interface UploadedStatement {
  name: string
  text: string
  accountId: string
}

/**
 * The browser sends multipart/form-data. Tests send the same fields as JSON: jsdom's XMLHttpRequest cannot pass a
 * multipart body through MSW (the stream never completes), see src/test/uploadShim.ts.
 */
async function readUpload(request: Request): Promise<UploadedStatement | null> {
  if (request.headers.get('content-type')?.includes('application/json')) {
    const body = (await request.json()) as { name: string; text: string; account_id?: string | null }
    return { name: body.name, text: body.text, accountId: body.account_id ?? '' }
  }
  const form = await request.formData()
  const file = form.get('file')
  if (!file || typeof file === 'string') return null
  return { name: file.name, text: await file.text(), accountId: String(form.get('account_id') ?? '') }
}

async function importStatement(request: Request) {
  if (getMockScenario() === 'ratelimit') {
    return errorResponse(429, 'validation', 'Слишком часто.')
  }
  const upload = await readUpload(request)
  if (!upload) return errorResponse(422, 'validation', 'Файл не передан.', { reason: 'empty' })
  const name = upload.name.toLowerCase()
  const text = upload.text
  if (name.includes('fail')) return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
  if (name.includes('slow')) await delay(4000)
  if (text.trim() === '') return errorResponse(422, 'validation', 'Файл пустой.', { reason: 'empty' })
  if (!text.includes('1CClientBankExchange')) {
    return errorResponse(422, 'validation', 'Файл не в формате 1С.', { reason: 'unsupported_format' })
  }
  if (name.includes('mismatch')) {
    return errorResponse(422, 'validation', 'В выписке другой счёт.', { reason: 'account_mismatch', account_tail: '7972' })
  }
  const store = getStore()
  const accountId = upload.accountId || 'A-bank'
  const account = ACCOUNT_REFS[accountId] ?? ACCOUNT_REFS['A-bank']!
  const base = { account, period: { from: '2026-08-01', to: '2026-09-09' } }
  if (store.importedFiles.has(text)) {
    const again: ImportResult = { import_id: newId('imp'), ...base, loaded: 0, duplicates: 0, to_check: 0, already_loaded: 29, skipped: 0 }
    return HttpResponse.json(again)
  }
  store.importedFiles.add(text)
  store.transactions.push(
    { ...baseImported('Оплата по счету 4519', -3100000), counterparty: 'Вет-Снаб', status: 'check' },
    { ...baseImported('Оплата по счету 12/Б', -1750000), counterparty: 'Вет-Снаб', status: 'check' },
    baseImported('Поступление по терминалу, эквайринг', 5800000, 'c-acq'),
  )
  const result: ImportResult = {
    import_id: newId('imp'),
    ...base,
    loaded: 148,
    duplicates: 3,
    to_check: 12,
    already_loaded: 0,
    skipped: name.includes('skip') ? 2 : 0,
  }
  return HttpResponse.json(result)
}

function baseImported(description: string, amount: number, categoryId: string | null = null): StoredTx {
  return {
    id: newId('t'),
    date: '2026-09-09',
    description,
    categoryId,
    accountId: 'A-bank',
    source: 'bank',
    amount,
    kind: amount < 0 ? 'out' : 'in',
    status: 'ok',
    counterparty: null,
    byHand: false,
    duplicateOfId: null,
    duplicateReason: null,
    duplicateState: null,
  }
}

export const transactionHandlers = [
  http.get('*/v1/transactions/counts', async ({ request }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    return HttpResponse.json(getMockScenario() === 'txempty' ? { all: 0, check: 0, duplicates: 0 } : counts())
  }),
  http.get('*/v1/transactions/summary', async ({ request }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    const month = new URL(request.url).searchParams.get('month')
    return HttpResponse.json(month === '2026-09' && getMockScenario() !== 'txempty' ? summarySeptember : summaryEmpty)
  }),
  http.get('*/v1/transactions/:id/rule-preview', async ({ request, params }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    const target = getStore().transactions.find((t) => t.id === params.id)
    if (!target) return errorResponse(404, 'not_found', 'Операция не найдена.')
    if (!target.counterparty) {
      return HttpResponse.json({ can_create: false, already_exists: false, match_text: null, matches_count: 0 })
    }
    const exists = getStore().rules.some((rule) => rule.matchText === target.counterparty)
    return HttpResponse.json({
      can_create: !exists,
      already_exists: exists,
      match_text: target.counterparty,
      matches_count: ruleMatches(target.counterparty, target.id).length,
    })
  }),
  http.get('*/v1/transactions', async ({ request }) => (await checked(request)) ?? listTransactions(new URL(request.url))),
  http.post('*/v1/transactions/:id/resolve-duplicate', async ({ request, params }) => (await checked(request)) ?? resolveDuplicate(request, String(params.id))),
  http.patch('*/v1/transactions/:id', async ({ request, params }) => (await checked(request)) ?? patchTransaction(request, String(params.id))),
  http.post('*/v1/transactions', async ({ request }) => (await checked(request)) ?? createTransaction(request)),
  http.get('*/v1/categories', async ({ request }) => (await guard(request)) ?? HttpResponse.json({ items: CATEGORIES })),
  http.get('*/v1/category-rules', async ({ request }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    return HttpResponse.json({ items: getMockScenario() === 'txempty' ? [] : getStore().rules.map(ruleDto) })
  }),
  http.delete('*/v1/category-rules/:id', async ({ request, params }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    const store = getStore()
    const before = store.rules.length
    store.rules = store.rules.filter((rule) => rule.id !== params.id)
    return store.rules.length === before ? errorResponse(404, 'not_found', 'Правило не найдено.') : new HttpResponse(null, { status: 204 })
  }),
  http.post('*/v1/imports/bank-statement', async ({ request }) => (await checked(request)) ?? importStatement(request)),
]
