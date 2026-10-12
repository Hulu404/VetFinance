// Mock data of the dashboard = the numbers of design/screens/dashboard.md (section "Подсказки"), as_of 2026-09-09, kopecks.
// The numbers agree with each other (written by hand): 341 300 + 71 500 = 412 800; 397 400 + 15 400 = 412 800;
// 201 300 + 128 700 = 330 000; 128 000 + 92 400 + 42 500 + 18 100 = 281 000; 330 000 - 281 000 = 49 000 (14,8%);
// runway = floor(412 800 * 28 / 1 050 000) = 11. Shapes follow the final contract (docs/handoff.md, 2026-10-12).
// Numbers are literals: the client never computes money.
import type { Account, AccountList, Advice, Clinic, Dashboard, Figure } from '../api/types'

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

const NBSP = ' '
/** Money in texts is written with non-breaking spaces, as the backend does (design/screens/dashboard.md). */
const nb = (text: string): string => text.replace(/(\d) (?=\d{3})/g, `$1${NBSP}`).replace(/ ₽/g, `${NBSP}₽`)

const rub = (label: string, value: number, delta?: boolean) => ({
  label,
  value,
  unit: 'rub' as const,
  ...(delta ? { delta } : {}),
})
const count = (label: string, value: number) => ({ label, value, unit: 'count' as const })

const BALANCE_SOURCE: Figure['source'] = ['bank', 'manual']

const total: Figure = {
  value: 41280000,
  unit: 'rub',
  breakdown: [rub('Расчётный счёт · Т-Банк 7972', 34130000), rub('Касса клиники', 7150000)],
  source: BALANCE_SOURCE,
  note: 'Остаток на конец 9 сентября по выписке банка и данным кассы.',
}

const bank: Figure = {
  value: 34130000,
  unit: 'rub',
  breakdown: [rub('Расчётный счёт · Т-Банк 7972', 34130000)],
  source: ['bank'],
  note: 'Остаток на конец 9 сентября по выписке банка. Последняя выписка: по 9 сентября.',
}

const cash: Figure = {
  value: 7150000,
  unit: 'rub',
  breakdown: [
    rub('Неделю назад', 7062000),
    rub('Внесено за смены', 6820000, true),
    rub('Расходы наличными', -732000),
    rub('Отправлено в банк', -6000000),
  ],
  source: ['manual'],
  note: 'Последняя инкассация 8 сентября.',
}

// Contract: breakdown = the change of every account (delta), details = the two balances that were compared.
const weekChange: Figure = {
  value: 1540000,
  unit: 'rub',
  delta: true,
  breakdown: [rub('Расчётный счёт · Т-Банк 7972', 1452000, true), rub('Касса клиники', 88000, true)],
  details: [rub('Неделю назад (2 сентября)', 39740000), rub('Сейчас', 41280000)],
  source: BALANCE_SOURCE,
  note: 'Сравниваем остаток на конец 9 сентября и на конец 2 сентября.',
}

const weekChangePct: Figure = {
  value: 3.9,
  unit: 'pct',
  delta: true,
  breakdown: [rub('Неделю назад (2 сентября)', 39740000), rub('Сейчас', 41280000)],
  source: BALANCE_SOURCE,
  note: nb('Изменение 15 400 ₽ к остатку неделю назад: 15 400 ÷ 397 400 = 3,9%.'),
}

const runway: Figure = {
  value: 11,
  unit: 'days',
  breakdown: [
    rub('Остаток на счетах', 41280000),
    rub('Расходы за 28 дней', 105000000),
    rub('Расходы в день, в среднем', 3750000),
    { label: 'Окно расчёта', value: 28, unit: 'days' as const },
  ],
  source: BALANCE_SOURCE,
  note: nb(
    '412 800 ₽ × 28 ÷ 1 050 000 ₽ ≈ 11,0: берём целые дни. Платежи вперёд не учтены: смотрите платёжный календарь.',
  ),
}

const revenue: Figure = {
  value: 33000000,
  unit: 'rub',
  breakdown: [rub('Услуги', 20130000), rub('Товары', 12870000)],
  details: [rub('Средний чек', 214286), count('Приёмов', 154)],
  source: ['vetmanager'],
  note: 'Закрытые счета Ветменеджера за 1–9 сентября, черновики не входят.',
}

const expenses: Figure = {
  value: 28100000,
  unit: 'rub',
  breakdown: [
    rub('Зарплаты и проценты', 12800000),
    rub('Препараты и корма', 9240000),
    rub('Расходники и хозтовары', 4250000),
    rub('Прочее', 1810000),
  ],
  source: ['bank', 'manual'],
  note: 'Деньги по операциям банка и кассы за 1–9 сентября, без переводов между счетами и дублей.',
}

const profit: Figure = {
  value: 4900000,
  unit: 'rub',
  breakdown: [rub('Выручка', 33000000, true), rub('Расходы', -28100000)],
  source: ['bank', 'vetmanager', 'manual'],
  note: 'Выручка минус расходы за 1–9 сентября. Налоги и амортизацию считает отчёт «Прибыль и убытки» при закрытии месяца.',
}

const margin: Figure = {
  value: 14.8,
  unit: 'pct',
  breakdown: [rub('Прибыль', 4900000), rub('Выручка', 33000000)],
  source: ['bank', 'vetmanager', 'manual'],
  note: nb('49 000 ₽ ÷ 330 000 ₽. Норма для клиник такого размера: 12–20%.'),
}

const visits: Figure = {
  value: 154,
  unit: 'count',
  breakdown: [count('Врач 1', 62), count('Врач 2', 51), count('Врач 3', 41)],
  source: ['vetmanager'],
  note: 'Приёмы по закрытым счетам Ветменеджера за 1–9 сентября.',
}

const avgCheck: Figure = {
  value: 214286,
  unit: 'rub',
  breakdown: [rub('Выручка', 33000000), count('Счетов', 154)],
  source: ['vetmanager'],
  note: 'Выручка делится на число закрытых счетов Ветменеджера.',
}

const trend = [
  ['2026-08-27', 37120000],
  ['2026-08-28', 36480000],
  ['2026-08-29', 38250000],
  ['2026-08-30', 39100000],
  ['2026-08-31', 40560000],
  ['2026-09-01', 38870000],
  ['2026-09-02', 39740000],
  ['2026-09-03', 38100000],
  ['2026-09-04', 39450000],
  ['2026-09-05', 40970000],
  ['2026-09-06', 40320000],
  ['2026-09-07', 41050000],
  ['2026-09-08', 40890000],
  ['2026-09-09', 41280000],
] as const

const TREND_INFO = { note: 'Остаток на конец дня по банку и кассе.', source: BALANCE_SOURCE }

export const adviceA: Advice[] = [
  {
    id: 'cash_runway',
    severity: 'alert',
    icon: '🩸',
    title: 'Денег хватит на 11 дней при текущем темпе расходов',
    text: nb('На счетах 412 800 ₽, в среднем уходит 37 500 ₽ в день. Платежи вперёд эта оценка не учитывает.'),
    why: {
      summary: 'Остаток делим на средний расход в день за последние 28 дней.',
      steps: [
        nb('Остаток на счетах: 412 800 ₽.'),
        nb('Расходы за 28 дней: 1 050 000 ₽, в среднем 37 500 ₽ в день.'),
        nb('412 800 ₽ ÷ 37 500 ₽ ≈ 11,0 дня, берём целые дни: 11.'),
      ],
      sources: ['Банк и касса: остаток на 9 сентября', 'Операции банка и кассы за 28 дней'],
    },
  },
  {
    id: 'drug_share',
    severity: 'warning',
    icon: '💊',
    title: 'Препараты и корма съедают 28,0% выручки при норме до 25%',
    text: nb('Закупки за 1–9 сентября: 92 400 ₽ при выручке 330 000 ₽. Норма клиники: до 25%.'),
    why: {
      summary: 'Доля закупок препаратов и кормов в выручке выше нормы клиники.',
      steps: [
        nb('Закупки препаратов и кормов за 1–9 сентября: 92 400 ₽.'),
        nb('Выручка за тот же период: 330 000 ₽.'),
        nb('92 400 ₽ ÷ 330 000 ₽ = 28,0%. Норма клиники: 25%, это 82 500 ₽; превышение 9 900 ₽.'),
      ],
      sources: ['Операции банка и кассы за сентябрь', 'Закрытые счета Ветменеджера за сентябрь'],
    },
  },
  {
    id: 'revenue_drop',
    severity: 'warning',
    icon: '📈',
    title: 'Выручка за 9 дней на 17,5% ниже, чем в августе',
    text: nb('С 1 по 9 сентября 330 000 ₽ против 400 000 ₽ за те же дни августа.'),
    why: {
      summary: 'Сравниваем одинаковые периоды: первые 9 дней месяца.',
      steps: [
        nb('Выручка 1–9 сентября: 330 000 ₽.'),
        nb('Выручка 1–9 августа: 400 000 ₽.'),
        nb('330 000 ₽ ÷ 400 000 ₽ = 82,5%. Совет появляется, когда выручка ниже 85% прошлого месяца.'),
      ],
      sources: ['Закрытые счета Ветменеджера за август и сентябрь'],
    },
  },
  {
    id: 'margin_ok',
    severity: 'good',
    icon: '📈',
    title: 'Рентабельность месяца 14,8%, это выше нижней границы нормы 12%',
    text: nb('Прибыль за 1–9 сентября 49 000 ₽ при выручке 330 000 ₽.'),
    why: {
      summary: 'Прибыль месяца составляет больше 12% выручки.',
      steps: [
        nb('Выручка за 1–9 сентября: 330 000 ₽, расходы: 281 000 ₽.'),
        nb('Прибыль: 330 000 ₽ − 281 000 ₽ = 49 000 ₽.'),
        nb('49 000 ₽ ÷ 330 000 ₽ = 14,8%. Норма для клиник такого размера: 12–20%.'),
      ],
      sources: ['Операции банка и кассы за сентябрь', 'Закрытые счета Ветменеджера за сентябрь'],
    },
  },
]

export const dashboardA: Dashboard = {
  as_of: '2026-09-09',
  data_as_of: '2026-09-09T04:12:00+03:00',
  data_stale: false,
  balance: { total, bank, cash, week_change: weekChange, week_change_pct: weekChangePct, runway_days: runway },
  month: {
    revenue,
    expenses,
    profit,
    profit_margin_pct: margin,
    days_passed: 9,
    days_total: 30,
    visits,
    avg_check: avgCheck,
  },
  balance_trend: trend.map(([date, value]) => ({ date, value })),
  balance_trend_info: TREND_INFO,
  advice: adviceA,
}

/** Same numbers, but the backend marks the data as stale and the last load was yesterday. */
export const dashboardStale: Dashboard = { ...dashboardA, data_as_of: '2026-09-08T04:12:00+03:00', data_stale: true }

const emptyFigure = (unit: Figure['unit'], note: string): Figure => ({
  value: 0,
  unit,
  breakdown: [],
  source: ['manual'],
  note,
})

/** Month before any data: zero values with an empty breakdown (agreed with backend in docs/handoff.md). */
const emptyMonth: Dashboard['month'] = {
  revenue: emptyFigure('rub', 'Данных за месяц нет.'),
  expenses: emptyFigure('rub', 'Данных за месяц нет.'),
  profit: emptyFigure('rub', 'Данных за месяц нет.'),
  profit_margin_pct: emptyFigure('pct', 'Данных за месяц нет.'),
  visits: emptyFigure('count', 'Данных за месяц нет.'),
  days_passed: 9,
  days_total: 30,
}

/** Clinic without accounts: balance breakdown is empty, value 0. No month data, no trend, no advice. */
export const dashboardNoAccounts: Dashboard = {
  as_of: '2026-09-09',
  data_as_of: null,
  data_stale: false,
  balance: {
    total: emptyFigure('rub', 'Счетов нет.'),
    bank: emptyFigure('rub', 'Счетов нет.'),
    cash: emptyFigure('rub', 'Счетов нет.'),
    week_change: null,
    week_change_pct: null,
  },
  month: emptyMonth,
  balance_trend: [],
  balance_trend_info: TREND_INFO,
  advice: [],
}

const runwayAt = (balance: number): Figure => ({
  ...runway,
  value: 0,
  breakdown: [
    rub('Остаток на счетах', balance),
    rub('Расходы за 28 дней', 105000000),
    rub('Расходы в день, в среднем', 3750000),
    { label: 'Окно расчёта', value: 28, unit: 'days' as const },
  ],
})

/** Accounts exist, balance is exactly zero. */
export const dashboardZero: Dashboard = {
  ...dashboardA,
  balance: {
    total: {
      value: 0,
      unit: 'rub',
      breakdown: [rub('Расчётный счёт · Т-Банк 7972', 0), rub('Касса клиники', 0)],
      source: ['manual'],
      note: total.note,
    },
    bank: {
      value: 0,
      unit: 'rub',
      breakdown: [rub('Расчётный счёт · Т-Банк 7972', 0)],
      source: ['manual'],
      note: bank.note,
    },
    cash: { value: 0, unit: 'rub', breakdown: [], source: ['manual'], note: cash.note },
    week_change: null,
    week_change_pct: null,
    runway_days: runwayAt(0),
  },
}

export const dashboardNegative: Dashboard = {
  ...dashboardA,
  balance: {
    total: {
      value: -1230000,
      unit: 'rub',
      breakdown: [rub('Расчётный счёт · Т-Банк 7972', -1530000), rub('Касса клиники', 300000)],
      source: BALANCE_SOURCE,
      note: total.note,
    },
    bank: {
      value: -1530000,
      unit: 'rub',
      breakdown: [rub('Расчётный счёт · Т-Банк 7972', -1530000)],
      source: ['bank'],
      note: bank.note,
    },
    cash: { value: 300000, unit: 'rub', breakdown: [], source: ['manual'], note: cash.note },
    week_change: null,
    week_change_pct: null,
    runway_days: runwayAt(-1230000),
  },
}

/** Accounts and expenses exist, but the month has no data yet (first day, or nothing loaded). */
export const dashboardEmptyMonth: Dashboard = { ...dashboardA, data_as_of: null, month: emptyMonth, advice: [] }

/** No deviations: the list is empty. */
export const dashboardNoAdvice: Dashboard = { ...dashboardA, advice: [] }

/** Young clinic: three days of history, no change over a week, advice is not built yet. */
export const dashboardFewData: Dashboard = {
  ...dashboardA,
  balance: { total, bank, cash, week_change: null, week_change_pct: null, runway_days: runway },
  balance_trend: trend.slice(-3).map(([date, value]) => ({ date, value })),
  advice: [],
}

/** `runway_days` is absent: no expenses in the window. */
export const dashboardNoRunway: Dashboard = {
  ...dashboardA,
  balance: { total, bank, cash, week_change: weekChange, week_change_pct: weekChangePct },
}
