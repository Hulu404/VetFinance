// TEMPORARY. Stage 1 shapes that are not in backend/openapi.json yet.
// They follow docs/api-contract.md (stage 1 sections, checked 2026-10-12). backend/openapi.json still has only
// /v1/clinic, /v1/accounts and /v1/dashboard. When the backend publishes the stage 1 paths, run `npm run gen:api`
// and replace each interface here with an alias to `components['schemas'][...]` in types.ts; this file is then deleted.
import type { Figure } from './types'

export type TxSource = 'bank' | 'vetmanager' | 'bot' | 'manual'
export type TxKind = 'in' | 'out' | 'transfer'
export type TxStatus = 'ok' | 'check' | 'duplicate'
export type TxTab = 'all' | 'check' | 'duplicates'

export interface NamedRef {
  id: string
  name: string
}

export interface Suggestion {
  category: NamedRef
  reason: 'rule' | 'similar'
  text: string
}

export interface Transaction {
  id: string
  date: string
  description: string
  category: NamedRef | null
  account: NamedRef
  source: TxSource
  amount: number
  kind: TxKind
  status: TxStatus
  figure?: Figure | null
  /** The other operation of the pair (the contract calls it TransactionBrief: one level, no nested pair). */
  duplicate_of?: Transaction | null
  duplicate_reason?: string | null
  duplicate_state?: 'pending' | 'confirmed' | null
  suggestion?: Suggestion | null
}

export interface TransactionList {
  items: Transaction[]
  next_cursor: string | null
}

export interface TransactionCounts {
  all: number
  check: number
  duplicates: number
}

export interface TransactionSummary {
  income: Figure
  expense: Figure
  balance: Figure
}

export interface RulePreview {
  can_create: boolean
  already_exists: boolean
  match_text: string | null
  matches_count: number
}

export interface CreatedRule {
  id: string
  match_text: string
  category: NamedRef
  applied_count: number
}

export interface TransactionUpdateResult extends Transaction {
  rule?: CreatedRule | null
}

export interface CategoryRule {
  id: string
  /** `inn`: by the counterparty, `text`: by a substring of the purpose of payment. */
  match?: 'inn' | 'text'
  match_text: string
  direction?: 'in' | 'out' | null
  category: NamedRef
  applied_count: Figure
  created_at: string
}

export interface CategoryRuleList {
  items: CategoryRule[]
}

/** The contract has `income`, `variable` and `fixed`; `expense` is tolerated (the golden set uses it) and shown as "Расходы". */
export type CategoryType = 'income' | 'variable' | 'fixed' | 'expense'

export interface Category {
  id: string
  name: string
  type: CategoryType
  norm_min_pct?: number | null
  norm_max_pct?: number | null
}

export interface CategoryList {
  items: Category[]
}

export interface CreateTransactionBody {
  kind: 'in' | 'out'
  account_id: string
  category_id: string | null
  date: string
  /** Positive kopecks; the sign comes from `kind`. */
  amount: number
  comment: string | null
}

export interface ImportResult {
  import_id: string
  account: NamedRef
  period: { from: string; to: string }
  loaded: number
  duplicates: number
  to_check: number
  already_loaded: number
  skipped: number
}

export type SyncStatus = 'running' | 'success' | 'partial' | 'failed'
export type SyncErrorCode = 'invalid_key' | 'unreachable' | 'rate_limited' | 'unknown'

export interface SyncRun {
  id: string
  status: SyncStatus
  started_at: string
  finished_at: string | null
  error_code: SyncErrorCode | null
  counts: Figure | null
}

export interface BankAccountStatus {
  account: NamedRef
  last_statement_to: string | null
}

export interface Connection {
  id: string
  type: 'vetmanager' | 'bank'
  connected: boolean
  address: string | null
  key_hint: string | null
  schedule: { kind: 'nightly'; time: string } | null
  data_stale: boolean
  last_success_at: string | null
  last_run: SyncRun | null
  runs: SyncRun[]
  bank: { accounts: BankAccountStatus[] } | null
}

export interface ConnectionList {
  items: Connection[]
  next_cursor?: string | null
}

export interface ResolveDuplicateResult {
  kept: Transaction[]
  duplicates: Transaction[]
}

export interface SaveVetmanagerBody {
  address: string
  key?: string
}

export type AcquiringStatus = 'matched' | 'mismatch' | 'waiting' | 'no_statement' | 'no_payments'

export interface AcquiringDayMember {
  date: string
  card_payments: Figure
  commission: Figure
  expected: Figure
}

export interface AcquiringDay {
  /** Equal to `date_from`. */
  date?: string
  date_from: string
  date_to: string
  card_payments: Figure
  commission: Figure
  expected: Figure
  credited: Figure | null
  discrepancy: Figure | null
  status: AcquiringStatus
  expected_by: string | null
  reviewed: boolean
  /** Days of a group closed by one credit; the row above shows the totals of the group. */
  members?: AcquiringDayMember[]
}

export interface AcquiringReconciliation {
  settlement_days: { min: number; max: number }
  rate_pct?: number
  bank_covered_to: string | null
  summary: {
    card_payments: Figure
    commission: Figure
    credited: Figure
    discrepancy: Figure
    waiting: Figure
  }
  days: AcquiringDay[]
}

export interface AcquiringDayDetails {
  date_from?: string
  date_to?: string
  payments: { date?: string; description: string; amount: number }[]
  credits: { date: string; description: string; amount: number; transaction_id: string | null }[]
  review: { reviewed: boolean; note: string | null }
}
