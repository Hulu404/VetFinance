// Mock data = tests/golden/set01, clinic A, as_of 2026-09-09 (kopecks; see expected.json).
// Shapes follow docs/api-contract.md. Numbers are literals: the client never computes money.
import type { Account, AccountList, Clinic, Dashboard, Figure } from '../api/types'

export const clinicA: Clinic = {
  id: 'A',
  name: 'Клиника «Лапа» (набор A)',
  legal_entity: null,
  tax_regime: null,
  timezone: 'Europe/Moscow',
  safe_balance: 15000000,
}

const accountsA: Account[] = [
  { id: 'A-bank', name: 'Расчётный счёт', kind: 'bank', opening_balance: 125000037, opening_date: '2026-08-01' },
  { id: 'A-bank2', name: 'Резервный счёт', kind: 'bank', opening_balance: 30000000, opening_date: '2026-08-01' },
  { id: 'A-cash', name: 'Касса', kind: 'cash', opening_balance: 4532050, opening_date: '2026-08-01' },
]

export const accountListA: AccountList = { items: accountsA, next_cursor: null }

const totalNote = 'Остаток на 2026-09-09: остаток на начало плюс операции без дублей, счетов: 3.'
const bankNote = 'Остаток в банке на 2026-09-09: остаток на начало плюс операции без дублей, счетов: 2.'

export const dashboardA: Dashboard = {
  as_of: '2026-09-09',
  data_as_of: '2026-09-09T04:12:00+03:00',
  balance: {
    total: {
      value: 228265855,
      unit: 'rub',
      breakdown: [
        { label: 'Расчётный счёт', value: 169959280, unit: 'rub' },
        { label: 'Резервный счёт', value: 45012345, unit: 'rub' },
        { label: 'Касса', value: 13294230, unit: 'rub' },
      ],
      source: ['bank', 'vetmanager', 'manual'],
      note: totalNote,
    },
    bank: {
      value: 214971625,
      unit: 'rub',
      breakdown: [
        { label: 'Расчётный счёт', value: 169959280, unit: 'rub' },
        { label: 'Резервный счёт', value: 45012345, unit: 'rub' },
      ],
      source: ['bank'],
      note: bankNote,
    },
  },
}

/** Same numbers, but the backend marks the data as stale and the last load was yesterday. */
export const dashboardStale: Dashboard = { ...dashboardA, data_as_of: '2026-09-08T04:12:00+03:00', data_stale: true }

const emptyFigure = (note: string): Figure => ({ value: 0, unit: 'rub', breakdown: [], source: ['manual'], note })

/** Clinic without accounts: breakdown is empty, value 0 (agreed with backend in docs/handoff.md). */
export const dashboardNoAccounts: Dashboard = {
  as_of: '2026-09-09',
  data_as_of: null,
  balance: { total: emptyFigure('Счетов нет.'), bank: emptyFigure('Счетов нет.') },
}

/** Accounts exist, balance is exactly zero. */
export const dashboardZero: Dashboard = {
  ...dashboardA,
  balance: {
    total: {
      value: 0,
      unit: 'rub',
      breakdown: [
        { label: 'Расчётный счёт', value: 0, unit: 'rub' },
        { label: 'Касса', value: 0, unit: 'rub' },
      ],
      source: ['manual'],
      note: totalNote,
    },
    bank: {
      value: 0,
      unit: 'rub',
      breakdown: [{ label: 'Расчётный счёт', value: 0, unit: 'rub' }],
      source: ['manual'],
      note: bankNote,
    },
  },
}

export const dashboardNegative: Dashboard = {
  ...dashboardA,
  balance: {
    total: {
      value: -1230000,
      unit: 'rub',
      breakdown: [
        { label: 'Расчётный счёт', value: -1530000, unit: 'rub' },
        { label: 'Касса', value: 300000, unit: 'rub' },
      ],
      source: ['bank', 'manual'],
      note: totalNote,
    },
    bank: {
      value: -1530000,
      unit: 'rub',
      breakdown: [{ label: 'Расчётный счёт', value: -1530000, unit: 'rub' }],
      source: ['bank'],
      note: bankNote,
    },
  },
}
