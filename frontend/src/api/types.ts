// Single module for API types. Response shapes come from backend/openapi.json (npm run gen:api).
import type { components, paths } from './schema.gen'

type Schemas = components['schemas']

export type FigureItem = Schemas['FigureItemOut']
export type Figure = Schemas['FigureOut']
export type FigureUnit = Figure['unit']
export type FigureSource = Figure['source'][number]
export type Dashboard = Schemas['DashboardOut']
export type DashboardBalance = Dashboard['balance']
export type DashboardMonth = Dashboard['month']
export type Advice = Schemas['AdviceOut']
export type AdviceSeverity = Advice['severity']
export type TrendPoint = Schemas['TrendPointOut']
export type BalanceTrendInfo = Schemas['TrendInfoOut']
export type Clinic = Schemas['ClinicOut']
export type Account = Schemas['AccountOut']
export type AccountList = Schemas['AccountsOut']

export type NamedRef = Schemas['NamedRefOut']
export type Suggestion = Schemas['SuggestionOut']
export type Transaction = Schemas['TransactionOut']
export type TransactionBrief = Schemas['TransactionBriefOut']
export type TxSource = Transaction['source']
export type TxKind = Transaction['kind']
export type TxStatus = Transaction['status']
export type TransactionList = Schemas['TransactionListOut']
export type TransactionCounts = Schemas['TabCountsOut']
export type TxTab = keyof TransactionCounts
export type TransactionSummary = Schemas['SummaryOut']
export type RulePreview = Schemas['RulePreviewOut']
export type CreatedRule = Schemas['CreatedRuleOut']
export type TransactionUpdateResult = Schemas['TransactionPatchedOut']
export type CategoryRule = Schemas['CategoryRuleOut']
export type CategoryRuleList = Schemas['CategoryRulesOut']
export type Category = Schemas['CategoryOut']
export type CategoryType = Category['type']
export type CategoryList = Schemas['CategoriesOut']
export type CreateTransactionBody = Schemas['TransactionCreate']
export type ImportResult = Schemas['ImportOut']
export type SyncRun = Schemas['SyncRunOut']
export type SyncStatus = SyncRun['status']
export type SyncErrorCode = NonNullable<SyncRun['error_code']>
export type BankAccountStatus = Schemas['BankAccountStatusOut']
export type Connection = Schemas['ConnectionOut']
export type ConnectionList = Schemas['ConnectionsOut']
export type ResolveDuplicateResult = Schemas['ResolveDuplicateOut']
export type SaveVetmanagerBody = Schemas['VetmanagerBody']
export type AcquiringDayMember = Schemas['AcquiringMemberOut']
export type AcquiringDay = Schemas['AcquiringRowOut']
export type AcquiringStatus = AcquiringDay['status']
export type AcquiringReconciliation = Schemas['AcquiringOut']
export type AcquiringDayDetails = Schemas['AcquiringDayOut']

export type PnlReport = Schemas['PnlOut']
export type PnlRow = Schemas['PnlRowOut']
export type PnlDirection = Schemas['PnlDirectionOut']
export type PnlView = PnlReport['view']
export type ReportPeriod = Schemas['app__schemas_reports__PeriodOut']
export type ReportStatus = PnlReport['status']
export type PartialReason = PnlReport['partial_reasons'][number]
export type NormReport = Schemas['NormOut']
export type NormItem = Schemas['NormItemOut']
export type NormBounds = Schemas['NormBoundsOut']
export type StockReport = Schemas['StockOut']
export type StockExpiringRow = Schemas['ExpiringRowOut']
export type StockWrittenOffRow = Schemas['WrittenOffRowOut']
export type StockIdleBucket = Schemas['IdleBucketOut']
export type StockIdleKey = StockIdleBucket['key'] | 'all'
export type StockIdlePage = Schemas['StockIdleOut']
export type StockIdleItem = Schemas['IdleItemOut']
export type ReportName = 'pnl' | 'norm' | 'stock'
export type ExportFormat = 'xlsx' | 'pdf'

// Stage 4: planning
export type CalendarReport = Schemas['CalendarOut']
export type CalendarDay = Schemas['DayOut']
export type CalendarPayment = Schemas['PaymentOut']
export type CalendarAlert = Schemas['CalendarAlertOut']
export type MoveSuggestion = Schemas['MoveSuggestionOut']
export type CalendarStatus = CalendarReport['status']
export type CalendarPartialReason = CalendarReport['partial_reasons'][number]
export type DayStatus = CalendarDay['status']
export type PaymentSource = CalendarPayment['source']
export type ManualPaymentBody = Schemas['ManualPaymentBody']
export type ManualPayment = Schemas['ManualPaymentOut']
export type CounterpartyRef = Schemas['CounterpartyRefOut']
export type Counterparty = Schemas['CounterpartyOut']
export type ClinicPatch = Schemas['ClinicPatch']
export type ObligationsReport = Schemas['ObligationsOut']
export type Loan = Schemas['LoanOut']
export type Equipment = Schemas['EquipmentOut']
export type ObligationStatus = Loan['status']
export type ObligationBody = NonNullable<
  paths['/v1/obligations']['post']['requestBody']
>['content']['application/json']
export type ObligationPatchBody = NonNullable<
  paths['/v1/obligations/{obligation_id}']['patch']['requestBody']
>['content']['application/json']

/** Error codes from docs/api-contract.md. */
export type ApiErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'validation'
  | 'conflict'
  | 'sync_failed'

/** Error envelope from the contract: { "error": { code, message, details } }. */
export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> }
}
