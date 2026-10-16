// In-memory state of the mock backend for stage 1: operations, rules, imported files.
// It behaves like the future backend (statuses, rules, duplicates) so the screens can be checked end to end.
import type { Category, CategoryRule, NamedRef, Transaction, TransactionBrief, TxKind, TxSource, TxStatus } from '../api/types'
import { countFigure, rubFigure } from './figures'

const REPORT_DEFAULTS: Pick<Category, 'norm_key' | 'direction' | 'payroll'> = {
  norm_key: null, direction: null, payroll: false,
}

export const CATEGORIES: Category[] = [
  { ...REPORT_DEFAULTS, id: 'c-income', name: 'Выручка', type: 'income', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-acq', name: 'Выручка (эквайринг)', type: 'income', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-rent', name: 'Аренда', type: 'fixed', norm_min_pct: 6, norm_max_pct: 10, norm_key: 'rent' },
  { ...REPORT_DEFAULTS, id: 'c-drugs', name: 'Препараты', type: 'variable', norm_min_pct: 20, norm_max_pct: 28, norm_key: 'drugs', direction: 'goods' },
  { ...REPORT_DEFAULTS, id: 'c-lab', name: 'Лаборатория', type: 'variable', norm_min_pct: null, norm_max_pct: null, norm_key: 'lab', direction: 'services' },
  { ...REPORT_DEFAULTS, id: 'c-util', name: 'Коммунальные услуги', type: 'fixed', norm_min_pct: null, norm_max_pct: null, norm_key: 'rent' },
  { ...REPORT_DEFAULTS, id: 'c-tax', name: 'Налоги и взносы', type: 'tax', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-pay', name: 'Зарплата', type: 'fixed', norm_min_pct: null, norm_max_pct: null, payroll: true },
  { ...REPORT_DEFAULTS, id: 'c-bank', name: 'Банковские комиссии', type: 'variable', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-other', name: 'Прочие расходы', type: 'variable', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-loan', name: 'Платёж по кредиту', type: 'obligation', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-capex', name: 'Покупка оборудования', type: 'capex', norm_min_pct: null, norm_max_pct: null },
  { ...REPORT_DEFAULTS, id: 'c-owner', name: 'Вывод владельца', type: 'owner_draw', norm_min_pct: null, norm_max_pct: null },
]

export const ACCOUNT_REFS: Record<string, NamedRef> = {
  'A-bank': { id: 'A-bank', name: 'Расчётный счёт' },
  'A-bank2': { id: 'A-bank2', name: 'Резервный счёт' },
  'A-cash': { id: 'A-cash', name: 'Касса' },
}

export interface StoredTx {
  id: string
  date: string
  description: string
  categoryId: string | null
  accountId: keyof typeof ACCOUNT_REFS
  source: TxSource
  amount: number
  kind: TxKind
  status: TxStatus
  /** Counterparty text a rule can match; null when the payment has none. */
  counterparty: string | null
  /** Categorised by hand without a rule: a new rule must not touch it. */
  byHand: boolean
  duplicateOfId: string | null
  duplicateReason: string | null
  duplicateState: 'pending' | 'confirmed' | null
}

export interface StoredRule {
  id: string
  match: 'inn' | 'text'
  direction: 'in' | 'out' | null
  matchText: string
  categoryId: string
  appliedThisMonth: number
  appliedBefore: number
  createdAt: string
}

const SOURCE_LABEL: Record<TxSource, string> = {
  bank: 'Выписка банка',
  vetmanager: 'Ветменеджер',
  bot: 'Бот',
  manual: 'Внесено вручную',
}

function row(
  id: string,
  date: string,
  description: string,
  amount: number,
  options: Partial<StoredTx> = {},
): StoredTx {
  return {
    id,
    date,
    description,
    categoryId: null,
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
    ...options,
  }
}

/** Receipts of the days, kopecks; plain literals so the list is long enough for the "Показать ещё" button. */
const FILLER_RECEIPTS = [
  7100000, 6540000, 5890000, 7320000, 6015000, 4980000, 5560000, 6870000, 7450000, 5210000, 6390000, 5740000,
  6120000, 4860000, 5330000, 6640000, 7010000, 5470000, 6280000, 5920000, 6750000, 5080000, 6430000, 5690000,
  7260000, 4920000, 5810000, 6190000, 6910000, 5360000, 6070000, 5640000, 6520000, 4790000, 5950000, 6330000,
  7180000, 5280000, 6460000, 5730000,
]

function filler(): StoredTx[] {
  return FILLER_RECEIPTS.map((amount, index) =>
    row(`t-fill-${index + 1}`, `2026-09-0${(index % 9) + 1}`, `Оплата пациентов · эквайринг, смена ${index + 1}`, amount, {
      categoryId: 'c-acq',
    }),
  )
}

export function seedTransactions(): StoredTx[] {
  return [
    row('t-d1', '2026-09-09', 'Поступление по терминалу, эквайринг', 7100000, { categoryId: 'c-acq' }),
    row('t-d2', '2026-09-08', 'Оплата по счету 4471 за препараты', -2850000, {
      counterparty: 'Вет-Снаб',
      categoryId: 'c-drugs',
    }),
    row('t-d3', '2026-09-08', 'Оплата по счету 4490 за препараты', -2380000, {
      counterparty: 'Вет-Снаб',
      categoryId: 'c-drugs',
    }),
    row('t-d4', '2026-09-07', 'ИП Волков · аренда за сентябрь', -8500000, {
      counterparty: 'ИП Волков',
      categoryId: null,
      status: 'check',
    }),
    row('t-d5', '2026-09-07', 'Перевод между счетами', -5000000, { kind: 'transfer', accountId: 'A-bank' }),
    row('t-d5b', '2026-09-07', 'Перевод между счетами', 5000000, { kind: 'transfer', accountId: 'A-bank2' }),
    row('t-d6', '2026-09-06', 'Корма Роял Канин, 3 уп.', -540000, {
      categoryId: 'c-drugs',
      source: 'bank',
    }),
    row('t-d7', '2026-09-06', 'Роял Канин 3 упаковки', -540000, {
      categoryId: 'c-drugs',
      source: 'manual',
      status: 'duplicate',
      duplicateOfId: 't-d6',
      duplicateReason: 'одинаковая сумма 5 400 ₽, дата 6 сен, разные источники',
      duplicateState: 'pending',
    }),
    row('t-d8', '2026-09-05', 'Оплата по счету 88 за услуги', -1200000, {
      counterparty: 'Мед-Лаб',
      status: 'check',
    }),
    row('t-d9', '2026-09-05', 'Приём, терапия (наличные)', 240000, {
      accountId: 'A-cash',
      source: 'vetmanager',
      categoryId: 'c-income',
    }),
    row('t-d10', '2026-09-04', 'Такси за анализами', -64000, {
      accountId: 'A-cash',
      source: 'manual',
      status: 'check',
    }),
    row('t-d11', '2026-09-03', 'Оплата по счету 4400 за расходники', -1500000, {
      counterparty: 'Вет-Снаб',
      status: 'check',
    }),
    row('t-d12', '2026-09-03', 'Оплата услуг связи', -450000, {
      categoryId: 'c-other',
      status: 'duplicate',
      duplicateOfId: 't-d13',
      duplicateReason: 'одинаковая сумма 4 500 ₽, даты 2 и 3 сен, разные источники',
      duplicateState: 'pending',
      source: 'manual',
    }),
    row('t-d13', '2026-09-02', 'Услуги связи за август', -450000, { categoryId: 'c-other' }),
    row('t-d14', '2026-09-01', 'Налоговый платёж (единый налоговый платеж)', -3200000, { categoryId: 'c-tax' }),
    row('t-a1', '2026-08-28', 'Оплата поставщику, счёт 3901', -900000, {
      counterparty: 'ООО Фарм-Опт',
      status: 'check',
    }),
    row('t-a3', '2026-08-05', 'ИП Волков · аренда за август', -8500000, {
      counterparty: 'ИП Волков',
      status: 'check',
    }),
    row('t-a2', '2026-08-21', 'Оплата пациентов · эквайринг', 6200000, { categoryId: 'c-acq' }),
    ...filler(),
  ]
}

export const SEED_RULES: StoredRule[] = [
  { id: 'r-1', match: 'inn', direction: 'out', matchText: 'Мед-Лаб', categoryId: 'c-lab', appliedThisMonth: 4, appliedBefore: 37, createdAt: '2026-08-04' },
  { id: 'r-2', match: 'text', direction: 'in', matchText: 'эквайринг', categoryId: 'c-acq', appliedThisMonth: 52, appliedBefore: 160, createdAt: '2026-08-01' },
]

interface Store {
  transactions: StoredTx[]
  rules: StoredRule[]
  importedFiles: Set<string>
  nextId: number
}

function freshStore(): Store {
  return { transactions: seedTransactions(), rules: SEED_RULES.map((r) => ({ ...r })), importedFiles: new Set(), nextId: 1 }
}

let store = freshStore()

export function resetTxStore(): void {
  store = freshStore()
}

export function getStore(): Store {
  return store
}

export function newId(prefix: string): string {
  const id = `${prefix}-n${store.nextId}`
  store.nextId += 1
  return id
}

export function categoryRef(id: string | null): NamedRef | null {
  const found = CATEGORIES.find((category) => category.id === id)
  return found ? { id: found.id, name: found.name } : null
}

function accountLabel(accountId: string): string {
  return ACCOUNT_REFS[accountId]?.name ?? accountId
}

function toBriefDto(stored: StoredTx): TransactionBrief {
  return {
    id: stored.id,
    date: stored.date,
    description: stored.description,
    category: categoryRef(stored.categoryId),
    account: ACCOUNT_REFS[stored.accountId] ?? { id: stored.accountId, name: stored.accountId },
    source: stored.source,
    amount: stored.amount,
    kind: stored.kind,
    status: stored.status,
    figure: rubFigure(
      stored.amount,
      [[`${SOURCE_LABEL[stored.source]} · ${accountLabel(stored.accountId)}`, stored.amount]],
      [stored.source],
      stored.status === 'duplicate'
        ? 'Эта операция не входит в остаток и отчёты: она признана повтором другой.'
        : stored.categoryId
          ? `Статья «${categoryRef(stored.categoryId)?.name ?? ''}».`
          : 'Статья пока не назначена.',
    ),
    duplicate_state: stored.duplicateState,
  }
}

export function toDto(stored: StoredTx): Transaction {
  const original = stored.duplicateOfId ? store.transactions.find((t) => t.id === stored.duplicateOfId) : null
  return {
    ...toBriefDto(stored),
    duplicate_of: original ? toBriefDto(original) : null,
    duplicate_reason: stored.duplicateReason,
    suggestion: suggestionFor(stored),
  }
}

function suggestionFor(stored: StoredTx): Transaction['suggestion'] {
  if (stored.status !== 'check' || !stored.counterparty) return null
  const similar = store.transactions.filter(
    (other) => other.id !== stored.id && other.counterparty === stored.counterparty && other.categoryId,
  )
  const first = similar[0]
  if (!first) return null
  const category = categoryRef(first.categoryId)
  if (!category) return null
  return { category, reason: 'similar', text: `Так же разнесено ${similar.length} ${similar.length === 1 ? 'операция' : 'операции'} по «${stored.counterparty}»` }
}

export function ruleDto(rule: StoredRule): CategoryRule {
  return {
    id: rule.id,
    match: rule.match,
    match_text: rule.matchText,
    direction: rule.direction,
    category: categoryRef(rule.categoryId) ?? { id: rule.categoryId, name: rule.categoryId },
    applied_count: countFigure(
      rule.appliedThisMonth + rule.appliedBefore,
      [
        ['В этом месяце', rule.appliedThisMonth],
        ['Раньше', rule.appliedBefore],
      ],
      ['calc'],
      'Сколько операций правило разнесло само.',
    ),
    created_at: rule.createdAt,
  }
}

export function counts() {
  const rows = store.transactions
  return {
    all: rows.length,
    check: rows.filter((t) => t.status === 'check').length,
    duplicates: rows.filter((t) => t.duplicateState === 'pending').length,
  }
}

/** Operations a new rule would change: without a category, same counterparty, not set by hand. */
export function ruleMatches(counterparty: string, exceptId: string): StoredTx[] {
  return store.transactions.filter(
    (t) => t.id !== exceptId && t.counterparty === counterparty && t.categoryId === null && !t.byHand && t.status === 'check',
  )
}
