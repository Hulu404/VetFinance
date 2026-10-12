// Single module for API types. Response shapes come from backend/openapi.json (npm run gen:api).
import type { components } from './schema.gen'

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

export * from './stage1'

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
