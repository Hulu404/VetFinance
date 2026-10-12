// Single module for API types. Response shapes come from backend/openapi.json (npm run gen:api).
import type { components } from './schema.gen'

type Schemas = components['schemas']

export type Figure = Schemas['FigureOut']
export type FigureItem = Schemas['FigureItemOut']
export type FigureUnit = Figure['unit']
export type FigureSource = Figure['source'][number]
/** `data_stale` is requested from backend for stage 1 (docs/handoff.md); until it is in openapi it is optional here. */
export type Dashboard = Schemas['DashboardOut'] & { data_stale?: boolean }
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
