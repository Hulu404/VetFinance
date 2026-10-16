import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PnlReport } from '../../api/types'
import { pnlClinicExample } from '../../mocks/reportsFixtures'
import { setMockScenario } from '../../mocks/scenario'
import { server } from '../../mocks/server'
import { renderWithQuery } from '../../test/render'
import { LocationProbe, numbersWithoutTip, stubWidth } from '../../test/reports'
import { PnlPage } from './PnlPage'

const NBSP = String.fromCharCode(160)
const MINUS = '−'
const ROW_KEYS = ['revenue', 'variable', 'marginal_profit', 'fixed', 'fixed_payroll', 'fixed_other', 'taxes', 'obligations', 'net_profit']

function renderPnl(path = '/reports/pnl?month=2026-09') {
  return renderWithQuery(
    <>
      <PnlPage />
      <LocationProbe />
    </>,
    { path, toasts: true },
  )
}

async function loaded() {
  await screen.findAllByTestId('pnl-row')
}

const amountOf = (key: string) => document.querySelector(`[data-testid="pnl-row-amount"][data-key="${key}"]`) as HTMLElement
const shareOf = (key: string) => document.querySelector(`[data-testid="pnl-row-share"][data-key="${key}"]`) as HTMLElement

function serveReport(patch: (base: PnlReport) => PnlReport) {
  server.use(http.get('*/v1/reports/pnl', () => HttpResponse.json(patch(pnlClinicExample) as unknown as Record<string, unknown>)))
}

afterEach(() => {
  vi.unstubAllGlobals()
  server.events.removeAllListeners()
})

describe('PnlPage: the statement', () => {
  it('shows the loading state first: busy root, export disabled, hidden status text', () => {
    renderPnl()

    expect(screen.getByTestId('pnl')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Загружаем отчёт')).toBeInTheDocument()
    expect(screen.getByTestId('pnl-loading')).toBeInTheDocument()
    expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByTestId('pnl-export-pdf')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Прибыль и убытки')
  })

  it('lists the nine rows in order, with the obligations row and the real minus before expenses', async () => {
    renderPnl()
    await loaded()

    const keys = screen.getAllByTestId('pnl-row').map((row) => row.getAttribute('data-key'))
    expect(keys).toEqual(ROW_KEYS)
    expect(screen.getByTestId('pnl')).toHaveAttribute('aria-busy', 'false')
    expect(amountOf('revenue').textContent).toBe(`1${NBSP}098${NBSP}156,10${NBSP}₽`)
    expect(amountOf('variable').textContent).toBe(`${MINUS}562${NBSP}150,02${NBSP}₽`)
    expect(amountOf('fixed_payroll').textContent?.startsWith(MINUS)).toBe(true)
    expect(amountOf('marginal_profit').textContent?.startsWith(MINUS)).toBe(false)
    expect(amountOf('net_profit').textContent).toBe(`128${NBSP}544,93${NBSP}₽`)
    expect(shareOf('variable')).toHaveTextContent('51,2%')
    expect(screen.getByTestId('page-subtitle')).toHaveTextContent('Сентябрь 2026 · наведите на сумму, чтобы увидеть, из чего она состоит')
  })

  it('marks the kind of each row and shows the headline and the footnote from the API', async () => {
    renderPnl()
    await loaded()

    expect(screen.getAllByTestId('pnl-row').map((row) => row.getAttribute('data-kind'))).toEqual([
      'revenue',
      'expense',
      'subtotal',
      'expense',
      'child',
      'child',
      'expense',
      'expense',
      'total',
    ])
    expect(screen.getByTestId('pnl-headline')).toHaveTextContent('Клиника заработала 128 544,93 ₽ чистыми: 11,7% выручки, ниже нормы 12–20%.')
    expect(screen.getByTestId('pnl-footnote')).toHaveTextContent('= 128 544,93 ₽.')
    expect(screen.getByTestId('pnl-footnote')).toHaveTextContent('Амортизация не списывает деньги со счёта, но уменьшает прибыль.')
  })

  it('opens a tip with the breakdown, the note and the source from a row amount, by keyboard', async () => {
    const user = userEvent.setup()
    renderPnl()
    await loaded()

    within(amountOf('variable')).getByTestId('figure-tip-trigger').focus()

    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Переменные расходы')
    expect(tip).toHaveTextContent('−562 150,02 ₽ · 51,2%')
    expect(within(tip).getAllByTestId('figure-tip-row')).toHaveLength(5)
    expect(within(tip).getByTestId('figure-tip-source')).toHaveTextContent('Банк')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByTestId('figure-tip')).not.toBeInTheDocument())
  })

  it('gives every amount and every share a tip trigger and a data-figure path', async () => {
    renderPnl()
    await loaded()

    for (const key of ROW_KEYS) {
      expect(within(amountOf(key)).getByTestId('figure-tip-trigger'), `${key} amount`).toBeInTheDocument()
      expect(within(shareOf(key)).getByTestId('figure-tip-trigger'), `${key} share`).toBeInTheDocument()
    }
    expect(amountOf('net_profit')).toHaveAttribute('data-figure', 'rows.net_profit.amount')
    expect(shareOf('net_profit')).toHaveAttribute('data-figure', 'rows.net_profit.share_pct')
  })

  it('draws the structure bar with the six legend items, shares from the API', async () => {
    renderPnl()
    await loaded()

    const items = screen.getAllByTestId('pnl-structure-item')
    expect(items.map((item) => item.getAttribute('data-key'))).toEqual(['variable', 'fixed_payroll', 'fixed_other', 'taxes', 'obligations', 'net_profit'])
    expect(items[0]).toHaveTextContent('Переменные расходы51,2%')
    expect(items[1]).toHaveTextContent('ФОТ13,5%')
    expect(items[0]).toHaveAttribute('data-figure', 'rows.variable.share_pct')
    expect(screen.getByRole('img', { name: /Структура выручки: переменные расходы 51,2%, фот 13,5%/ })).toBeInTheDocument()
  })

  it('shows the month and the status pill; both neighbours are available in a closed month', async () => {
    renderPnl()
    await loaded()

    expect(screen.getByTestId('pnl-month')).toHaveTextContent('Сентябрь 2026')
    expect(screen.getByTestId('pnl-period-status')).toHaveTextContent('месяц закрыт')
    expect(screen.getByTestId('pnl-month-prev')).toHaveAttribute('aria-disabled', 'false')
    expect(screen.getByTestId('pnl-month-next')).toHaveAttribute('aria-disabled', 'false')
    expect(screen.queryByTestId('pnl-open-note')).not.toBeInTheDocument()
  })

  it('leaves no sum or percent without a tip, in either view, and no forbidden words', async () => {
    const user = userEvent.setup()
    renderPnl()
    await loaded()
    const main = screen.getByTestId('pnl')

    expect(numbersWithoutTip(main)).toEqual([])
    await user.click(screen.getByTestId('pnl-view-direction'))
    await waitFor(() => expect(screen.getAllByTestId('pnl-direction')).toHaveLength(4))
    expect(numbersWithoutTip(main)).toEqual([])
    expect(main.textContent?.toLowerCase()).not.toMatch(/\bии\b|роль|филиал|\bбот\b|катастроф|опасно/)
  })

  it('marks the obligations row "не заполнено" when the API says so', async () => {
    serveReport((base) => ({
      ...base,
      status: 'partial',
      partial_reasons: ['no_obligations'],
      rows: base.rows.map((row) => (row.key === 'obligations' ? { ...row, warning: 'no_obligations' as const } : row)),
    }))
    renderPnl()
    await loaded()

    expect(screen.getByTestId('pnl-row-warning')).toHaveTextContent('не заполнено')
    expect(screen.getByTestId('pnl-partial-banner')).toHaveTextContent('Не заполнены кредиты и оборудование: чистая прибыль может быть завышена.')
  })
})

describe('PnlPage: month, view and the address', () => {
  it('asks for the previous month and writes it into the address', async () => {
    const user = userEvent.setup()
    const asked: string[] = []
    server.events.on('request:start', ({ request }) => asked.push(request.url))
    renderPnl()
    await loaded()

    await user.click(screen.getByTestId('pnl-month-prev'))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-08'))
    await waitFor(() => expect(screen.getByTestId('pnl-month')).toHaveTextContent('Август 2026'))
    expect(asked.some((url) => url.includes('/v1/reports/pnl') && url.includes('month=2026-08'))).toBe(true)
  })

  it('does not go before the first month with data', async () => {
    const user = userEvent.setup()
    renderPnl('/reports/pnl?month=2026-07')
    await loaded()

    expect(screen.getByTestId('pnl-month-prev')).toHaveAttribute('aria-disabled', 'true')
    await user.click(screen.getByTestId('pnl-month-prev'))
    expect(screen.getByTestId('location')).toHaveTextContent('month=2026-07')
  })

  it('writes the month the API chose when the address has none or has garbage', async () => {
    renderPnl('/reports/pnl?month=garbage')

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-09'))
    expect(screen.queryByTestId('pnl-error')).not.toBeInTheDocument()
    await loaded()
  })

  it('replaces a month the API rejects by the default one, without a message', async () => {
    renderPnl('/reports/pnl?month=2027-05')

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-09'))
    await loaded()
    expect(screen.queryByTestId('pnl-error')).not.toBeInTheDocument()
  })

  it('passes as_of, month and view to the API', async () => {
    const asked: string[] = []
    server.use(
      http.get('*/v1/reports/pnl', ({ request }) => {
        asked.push(request.url)
        return HttpResponse.json({ error: { code: 'sync_failed', message: 'x', details: {} } }, { status: 500 })
      }),
    )
    renderPnl('/reports/pnl?month=2026-09&as_of=2026-09-30')

    await screen.findByTestId('pnl-error')
    expect(asked[0]).toContain('as_of=2026-09-30')
    expect(asked[0]).toContain('month=2026-09')
    expect(asked[0]).toContain('view=clinic')
  })

  it('switches to "Услуги и товары": the table of directions and the bridge to the profit', async () => {
    const user = userEvent.setup()
    renderPnl()
    await loaded()
    expect(screen.getByTestId('pnl-view-clinic')).toHaveAttribute('aria-checked', 'true')

    await user.click(screen.getByTestId('pnl-view-direction'))

    await waitFor(() => expect(screen.getAllByTestId('pnl-direction')).toHaveLength(4))
    expect(screen.getByTestId('pnl-view-direction')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('location')).toHaveTextContent('view=direction')
    const rowOf = (key: string) => document.querySelector(`[data-testid="pnl-direction"][data-key="${key}"]`) as HTMLElement
    expect(rowOf('services')).toHaveTextContent('Услуги')
    expect(within(rowOf('services')).getByTestId('pnl-direction-revenue').textContent).toBe(`641${NBSP}320,70${NBSP}₽`)
    expect(within(rowOf('services')).getByTestId('pnl-direction-costs').textContent?.startsWith(MINUS)).toBe(true)
    expect(rowOf('common')).toHaveTextContent('не относятся ни к услугам, ни к товарам')
    expect(within(rowOf('common')).getByTestId('pnl-direction-margin').textContent?.startsWith(MINUS)).toBe(true)
    expect(rowOf('total')).toHaveTextContent('Маржинальная прибыль')
    expect(within(rowOf('total')).getByTestId('pnl-direction-margin-pct')).toHaveTextContent('48,8%')
    expect(screen.getByText('От маржи до чистой прибыли')).toBeInTheDocument()
    expect(amountOf('net_profit')).toBeInTheDocument()
    expect(amountOf('revenue')).toBeNull()
    expect(screen.getByTestId('pnl-footnote')).toHaveTextContent('Закупка препаратов отнесена к товарам целиком')
    expect(screen.getAllByTestId('pnl-structure-item').map((item) => item.getAttribute('data-key'))).toEqual(['services', 'goods'])
  })

  it('gives every direction number a tip trigger', async () => {
    renderPnl('/reports/pnl?month=2026-09&view=direction')
    await waitFor(() => expect(screen.getAllByTestId('pnl-direction')).toHaveLength(4))

    for (const id of ['revenue', 'share', 'costs', 'margin', 'margin-pct']) {
      for (const cell of screen.getAllByTestId(`pnl-direction-${id}`)) {
        expect(within(cell).getByTestId('figure-tip-trigger')).toBeInTheDocument()
        expect(cell.getAttribute('data-figure')).toBeTruthy()
      }
    }
  })

  it('turns the directions into cards on a phone', async () => {
    stubWidth(390)
    renderPnl('/reports/pnl?month=2026-09&view=direction')

    await waitFor(() => expect(screen.getAllByTestId('pnl-direction')).toHaveLength(4))
    expect(document.querySelector('table.dir__table')).toBeNull()
    const goods = document.querySelector('[data-testid="pnl-direction"][data-key="goods"]') as HTMLElement
    expect(within(goods).getByTestId('pnl-direction-margin-pct')).toBeInTheDocument()
  })
})

describe('PnlPage: states', () => {
  it('shows the empty card for a month without data and keeps the month and the buttons', async () => {
    renderPnl('/reports/pnl?month=2000-01')

    const empty = await screen.findByTestId('pnl-empty')
    expect(empty).toHaveTextContent('За январь данных нет')
    expect(empty).toHaveTextContent('Загрузите выписку или подключите Ветменеджер: отчёт появится, когда за месяц будут данные.')
    expect(within(empty).getByRole('link', { name: 'Загрузить выписку' })).toHaveAttribute('href', '/transactions?import=1')
    expect(within(empty).getByRole('link', { name: 'Подключения' })).toBeInTheDocument()
    expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByTestId('pnl-month-prev')).toBeInTheDocument()
    expect(screen.queryByTestId('pnl-row')).not.toBeInTheDocument()
  })

  it('shows the error card with Retry, and Retry loads the report', async () => {
    const user = userEvent.setup()
    setMockScenario('error')
    renderPnl()

    const error = await screen.findByTestId('pnl-error')
    expect(error).toHaveAttribute('role', 'alert')
    expect(error).toHaveTextContent('Не получилось загрузить отчёт')
    expect(error).toHaveTextContent('Это сбой на нашей стороне, ваши данные не пострадали. Попробуйте ещё раз.')
    expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'true')

    setMockScenario('default')
    await user.click(screen.getByTestId('pnl-error-retry'))
    await loaded()
    expect(screen.queryByTestId('pnl-error')).not.toBeInTheDocument()
  })

  it('says the connection is lost in words for a network failure', async () => {
    setMockScenario('network')
    renderPnl()

    expect(await screen.findByTestId('pnl-error')).toHaveTextContent('Нет связи с сервером. Проверьте интернет и повторите.')
  })

  it('shows a loss as "Чистый убыток" on a red row and a bar of expenses without the profit segment', async () => {
    setMockScenario('reportloss')
    renderPnl()
    await loaded()

    const net = document.querySelector('[data-testid="pnl-row"][data-key="net_profit"]') as HTMLElement
    expect(net).toHaveTextContent('Чистый убыток')
    expect(net).toHaveClass('stmt__row--neg')
    expect(amountOf('net_profit').textContent?.startsWith(MINUS)).toBe(true)
    expect(screen.getByTestId('pnl-headline')).toHaveTextContent('В сентябре расходы были больше выручки на 40 000 ₽.')
    expect(screen.getAllByTestId('pnl-structure-item').map((item) => item.getAttribute('data-key'))).not.toContain('net_profit')
    expect(screen.getByTestId('pnl-structure')).toHaveTextContent('Расходы больше выручки на 40 000 ₽')
  })

  it('shows dashes instead of shares and no bar when there is no revenue', async () => {
    setMockScenario('reportzero')
    renderPnl()
    await loaded()

    expect(shareOf('variable').textContent).toBe('—')
    expect(within(shareOf('variable')).queryByTestId('figure-tip-trigger')).not.toBeInTheDocument()
    expect(screen.queryByTestId('pnl-structure')).not.toBeInTheDocument()
    expect(screen.getByTestId('pnl-headline')).toHaveTextContent('выручки нет')
  })

  it('shows at most two partial-data strips, in the order of the API, with links', async () => {
    setMockScenario('reportpartial')
    renderPnl()
    await loaded()

    const banners = screen.getAllByTestId('pnl-partial-banner')
    expect(banners).toHaveLength(2)
    expect(banners[0]).toHaveTextContent('Нет данных Ветменеджера за сентябрь: выручка может быть занижена.')
    expect(within(banners[0] as HTMLElement).getByRole('link', { name: 'Проверить подключения' })).toBeInTheDocument()
    expect(banners[1]).toHaveTextContent('Выписка банка покрывает сентябрь не целиком: расходы могут быть занижены.')
    expect(within(banners[1] as HTMLElement).getByRole('link', { name: 'Загрузить выписку' })).toBeInTheDocument()
  })

  it('shows the stale-data strip from the dashboard answer', async () => {
    setMockScenario('stale')
    renderPnl()
    await loaded()

    const banner = await screen.findByTestId('pnl-stale-banner')
    expect(banner).toHaveTextContent('и могли устареть.')
    expect(within(banner).getByRole('link', { name: 'Проверить подключения' })).toBeInTheDocument()
  })

  it('keeps the numbers and puts a strip above them when a refresh fails', async () => {
    const { queryClient } = renderPnl()
    await loaded()

    server.use(http.get('*/v1/reports/pnl', () => HttpResponse.json({ error: { code: 'sync_failed', message: 'x', details: {} } }, { status: 500 })))
    await queryClient.refetchQueries({ queryKey: ['pnl'] }).catch(() => undefined)

    const banner = await screen.findByTestId('pnl-refresh-banner')
    expect(banner).toHaveTextContent('Не удалось обновить. Показаны данные на 04:12.')
    expect(within(banner).getByRole('button', { name: 'Обновить' })).toBeInTheDocument()
    expect(amountOf('revenue')).toBeInTheDocument()
    expect(screen.queryByTestId('pnl-error')).not.toBeInTheDocument()
  })
})

describe('PnlPage: the open month', () => {
  it('says the month is going, starts the headline with the date and shows the permanent note', async () => {
    setMockScenario('reportopen')
    renderPnl('/reports/pnl?month=2026-09')
    await loaded()

    expect(screen.getByTestId('pnl-period-status')).toHaveTextContent('месяц идёт, данные по 9 сентября')
    expect(screen.getByTestId('pnl-headline')).toHaveTextContent('К 9 сентября клиника заработала 91 600 ₽ чистыми: 17,6% выручки.')
    expect(screen.getByTestId('pnl-open-note')).toHaveTextContent(
      'Месяц ещё идёт: обязательства и амортизация взяты за весь месяц, налоги — только уплаченные на 9 сентября. К концу месяца прибыль изменится.',
    )
    expect(screen.getByTestId('pnl-headline').textContent).not.toMatch(/нормы/)
    expect(amountOf('taxes').textContent).toBe(`0${NBSP}₽`)
    expect(screen.getByTestId('pnl-month-next')).toHaveAttribute('aria-disabled', 'true')
  })
})

describe('PnlPage: export', () => {
  it('turns a 501 of the backend into the usual error toast and frees the buttons', async () => {
    const user = userEvent.setup()
    setMockScenario('exportfail')
    renderPnl()
    await loaded()

    await user.click(screen.getByTestId('pnl-export-xlsx'))

    expect(await screen.findByText('Не получилось подготовить файл. Попробуйте ещё раз.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'false'))
  })
})
