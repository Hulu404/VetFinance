import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { PnlReport, PnlRow } from '../api/types'
import {
  buildNorm,
  buildPnl,
  buildStock,
  lastClosedMonth,
  normExample,
  pnlClinicExample,
  pnlDirectionExample,
  stockExample,
  stockIdleExample,
} from './reportsFixtures'

// The mock is a fake backend: these tests keep its numbers consistent with the identities of docs/api-contract.md,
// so that a screen built on it shows a report that adds up. The client itself never does this arithmetic.

const amount = (report: PnlReport, key: string): number => (report.rows.find((row) => row.key === key) as PnlRow).amount.value

const openapiPath = resolve(__dirname, '../../../backend/openapi.json')
it.skipIf(!existsSync(openapiPath))('report mocks match the published API examples', () => {
  const schemas = JSON.parse(readFileSync(openapiPath, 'utf8')).components.schemas
  expect(pnlDirectionExample).toEqual(schemas.PnlOut.example)
  const clinic = structuredClone(schemas.PnlOut.example)
  clinic.view = 'clinic'
  delete clinic.directions
  delete clinic.common_variable
  expect(pnlClinicExample).toEqual(clinic)
  expect(normExample).toEqual(schemas.NormOut.example)
  expect(stockExample).toEqual(schemas.StockOut.example)
  expect(stockIdleExample).toEqual(schemas.StockIdleOut.example)
})

function expectIdentity(report: PnlReport) {
  const net = amount(report, 'revenue') - amount(report, 'variable') - amount(report, 'fixed') - amount(report, 'taxes') - amount(report, 'obligations')
  expect(amount(report, 'net_profit')).toBe(net)
  expect(amount(report, 'marginal_profit')).toBe(amount(report, 'revenue') - amount(report, 'variable'))
  const fixed = report.rows.find((row) => row.key === 'fixed') as PnlRow
  const parts = (fixed.children ?? []).reduce((sum, child) => sum + child.amount.value, 0)
  expect(parts).toBe(fixed.amount.value)
}

describe('report mocks', () => {
  it('the example of the contract adds up in both views', () => {
    expectIdentity(pnlClinicExample)
    expectIdentity(pnlDirectionExample)
  })

  it('the bridge of the directions holds in the example', () => {
    const [services, goods] = pnlDirectionExample.directions ?? []
    const common = pnlDirectionExample.common_variable?.value ?? 0
    expect((services?.revenue.value ?? 0) + (goods?.revenue.value ?? 0)).toBe(amount(pnlDirectionExample, 'revenue'))
    expect((services?.direct_costs.value ?? 0) + (goods?.direct_costs.value ?? 0) + common).toBe(amount(pnlDirectionExample, 'variable'))
    expect((services?.margin.value ?? 0) + (goods?.margin.value ?? 0) - common).toBe(amount(pnlDirectionExample, 'marginal_profit'))
  })

  it('the open month and the loss add up', () => {
    const open = buildPnl({ month: '2026-09', asOf: '2026-09-09', view: 'clinic', scenario: 'reportopen' })
    expect(open.period.status).toBe('open')
    expect(open.period.to).toBe('2026-09-09')
    expectIdentity(open)
    const loss = buildPnl({ month: '2026-09', asOf: '2026-10-01', view: 'clinic', scenario: 'reportloss' })
    expectIdentity(loss)
    expect(amount(loss, 'net_profit')).toBeLessThan(0)
  })

  it('every figure has a breakdown, a note and a source, except a zero value', () => {
    const reports = [pnlClinicExample, buildPnl({ month: '2026-09', asOf: '2026-09-09', view: 'clinic', scenario: 'reportopen' }), buildPnl({ month: '2026-09', asOf: '2026-10-01', view: 'clinic', scenario: 'reportloss' })]
    for (const report of reports) {
      for (const row of [...report.rows, ...report.rows.flatMap((item) => item.children ?? [])]) {
        for (const figure of [row.amount, row.share_pct]) {
          if (!figure || figure.value === 0) continue
          expect(figure.breakdown.length, `${row.key} breakdown`).toBeGreaterThan(0)
          expect(figure.source.length, `${row.key} source`).toBeGreaterThan(0)
          expect(figure.note.length, `${row.key} note`).toBeGreaterThan(0)
        }
      }
    }
  })

  it('the norm example keeps the shares of the rows without the memo row at the revenue', () => {
    const shares = normExample.items.filter((item) => !item.memo).reduce((sum, item) => sum + item.actual_pct.value, 0)
    expect(Math.abs(shares - 100)).toBeLessThanOrEqual(0.2)
    expect(normExample.items.filter((item) => item.memo).map((item) => item.key)).toEqual(['writeoff'])
  })

  it('the open month of the norm has no statuses, tones and deviations, but keeps the norms', () => {
    const open = buildNorm({ month: '2026-09', asOf: '2026-09-09', scenario: 'reportopen' })
    for (const item of open.items) {
      expect('status' in item).toBe(false)
      expect('tone' in item).toBe(false)
      expect('deviation_pp' in item).toBe(false)
      expect('deviation_rub' in item).toBe(false)
    }
    expect(open.items.find((item) => item.key === 'rent')?.norm?.min_pct).toBe(5)
  })

  it('the stock example: intervals add up to the frozen sum, expiring rows to the card, no expired batch among them', () => {
    const buckets = stockExample.idle_buckets.reduce((sum, bucket) => sum + bucket.amount.value, 0)
    expect(buckets).toBe(stockExample.frozen.value)
    const batches = stockExample.expiring.reduce((sum, row) => sum + row.amount.value, 0)
    expect(batches).toBe(stockExample.expiring_60d.value)
    expect(stockExample.expiring.every((row) => row.days_left >= 0)).toBe(true)
    expect(stockExample.expired_items.every((row) => row.days_left < 0)).toBe(true)
    expect(stockIdleExample.items.length).toBe(stockExample.frozen_positions.value)
    expect(buildStock({ scenario: 'default', asOf: null, month: null }).status).toBe('ok')
  })

  it('picks the last closed month by the reference date', () => {
    expect(lastClosedMonth('2026-10-01')).toBe('2026-09')
    expect(lastClosedMonth('2026-09-30')).toBe('2026-09')
    expect(lastClosedMonth('2026-09-09')).toBe('2026-08')
    expect(lastClosedMonth('2027-01-15')).toBe('2026-12')
  })
})
