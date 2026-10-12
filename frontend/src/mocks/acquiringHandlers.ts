// Reconciliation mock = the numbers of design/screens/acquiring.md (they add up there; the client never checks them).
import { http, HttpResponse } from 'msw'
import type { AcquiringDay, AcquiringDayDetails, AcquiringReconciliation } from '../api/types'
import { rubFigure } from './figures'
import { errorResponse, guard } from './guard'
import { getMockScenario } from './scenario'

const reviewed = new Map<string, string | null>()

export function resetAcquiringState(): void {
  reviewed.clear()
}

function day(
  from: string,
  to: string,
  payments: number,
  commission: number,
  expected: number,
  credited: number | null,
  status: AcquiringDay['status'],
  expectedBy: string | null,
): AcquiringDay {
  const discrepancy = credited === null ? null : credited - expected
  return {
    date_from: from,
    date_to: to,
    card_payments: rubFigure(payments, [['Банковские карты', payments]], ['vetmanager'], 'Оплаты картой из Ветменеджера за день.'),
    commission: rubFigure(commission, [['По ставке 1,9%', commission]], ['calc'], 'Ставка банка 1,9%: настройка клиники.'),
    expected: rubFigure(
      expected,
      [
        ['Оплаты', payments],
        ['Комиссия', -commission],
      ],
      ['calc'],
      expectedBy ? `Зачисление ожидаем до ${expectedBy}.` : 'Оплаты за вычетом комиссии.',
    ),
    credited:
      credited === null
        ? null
        : rubFigure(credited, credited > 0 ? [[`Зачисление банка`, credited]] : [], ['bank'], 'Зачисления эквайринга по выписке.'),
    discrepancy:
      discrepancy === null
        ? null
        : rubFigure(
            discrepancy,
            [
              ['Ожидали', expected],
              ['Зачислено', credited ?? 0],
            ],
            ['calc'],
            'Зачислено минус ожидаем.',
          ),
    status,
    expected_by: expectedBy,
    reviewed: reviewed.has(from),
  }
}

function septemberDays(): AcquiringDay[] {
  return [
    day('2026-09-09', '2026-09-09', 5200000, 98800, 5101200, null, 'waiting', '2026-09-14'),
    day('2026-09-08', '2026-09-08', 7100000, 134900, 6965100, null, 'waiting', '2026-09-11'),
    day('2026-09-04', '2026-09-06', 24400000, 463600, 23936400, 23812400, 'mismatch', '2026-09-09'),
    day('2026-09-03', '2026-09-03', 6000000, 114000, 5886000, 5886000, 'matched', '2026-09-08'),
    day('2026-09-02', '2026-09-02', 3000000, 57000, 2943000, 0, 'mismatch', '2026-09-07'),
  ]
}

function withoutStatement(days: AcquiringDay[]): AcquiringDay[] {
  return days.map((item) =>
    item.date_from > '2026-09-03'
      ? { ...item, status: 'no_statement' as const, credited: null, discrepancy: null }
      : item,
  )
}

function summary(): AcquiringReconciliation['summary'] {
  return {
    card_payments: rubFigure(45700000, [['2–9 сентября', 45700000]], ['vetmanager'], 'Оплаты картой за месяц из Ветменеджера.'),
    commission: rubFigure(868300, [['По ставке 1,9%', 868300]], ['calc'], 'Тариф банка 1,9%: настройка клиники.'),
    credited: rubFigure(29698400, [['Зачисления банка', 29698400]], ['bank'], 'Зачисления эквайринга по выписке.'),
    discrepancy: rubFigure(
      -3067000,
      [
        ['4–6 сентября', -124000],
        ['2 сентября', -2943000],
      ],
      ['calc'],
      'Зачислено минус ожидаем по дням, где зачисление уже должно было прийти.',
    ),
    waiting: rubFigure(
      12066300,
      [
        ['9 сентября', 5101200],
        ['8 сентября', 6965100],
      ],
      ['calc'],
      'Оплаты за вычетом комиссии за дни, когда зачисление ещё не должно было прийти.',
    ),
  }
}

function reconciliation(month: string): AcquiringReconciliation {
  const scenario = getMockScenario()
  const noPayments = scenario === 'acqempty' || month !== '2026-09'
  const days = noPayments ? [] : scenario === 'nostatement' ? withoutStatement(septemberDays()) : septemberDays()
  const empty = rubFigure(0, [], ['vetmanager'], 'Оплат картой за этот месяц нет.')
  return {
    settlement_days: { min: 1, max: 3 },
    bank_covered_to: scenario === 'nostatement' ? '2026-09-03' : '2026-09-09',
    summary: noPayments
      ? { card_payments: empty, commission: empty, credited: empty, discrepancy: empty, waiting: empty }
      : summary(),
    days,
  }
}

function details(date: string): AcquiringDayDetails {
  const isGroup = date === '2026-09-04'
  return {
    payments: isGroup
      ? [
          { date: '2026-09-04', description: 'Приём · терапия', amount: 240000 },
          { date: '2026-09-04', description: 'Вакцинация', amount: 160000 },
          { date: '2026-09-05', description: 'Хирургия, кастрация', amount: 1200000 },
          { date: '2026-09-06', description: 'Стоматология', amount: 840000 },
        ]
      : [
          { description: 'Приём · терапия', amount: 240000 },
          { description: 'Анализы', amount: 380000 },
        ],
    credits: isGroup
      ? [{ date: '2026-09-07', description: 'Расчётный счёт · зачисление эквайринга', amount: 23812400, transaction_id: 't-fill-1' }]
      : [],
    review: { reviewed: reviewed.has(date), note: reviewed.get(date) ?? null },
  }
}

async function checked(request: Request) {
  const blocked = await guard(request)
  if (blocked) return blocked
  if (getMockScenario() === 'acqerror') return errorResponse(500, 'sync_failed', 'Сбой на стороне сервера.')
  return null
}

export const acquiringHandlers = [
  http.get('*/v1/acquiring/reconciliation', async ({ request }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    const month = new URL(request.url).searchParams.get('month') ?? '2026-09'
    return HttpResponse.json(reconciliation(month))
  }),
  http.get('*/v1/acquiring/days/:date', async ({ request, params }) => (await checked(request)) ?? HttpResponse.json(details(String(params.date)))),
  http.post('*/v1/acquiring/days/:date/review', async ({ request, params }) => {
    const blocked = await checked(request)
    if (blocked) return blocked
    const body = (await request.json()) as { note?: string | null }
    reviewed.set(String(params.date), body.note ?? null)
    return HttpResponse.json(details(String(params.date)))
  }),
]
