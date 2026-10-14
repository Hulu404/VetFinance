import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { Dashboard, Figure } from '../api/types'
import { dashboardA } from '../mocks/fixtures'
import { setMockScenario } from '../mocks/scenario'
import { server } from '../mocks/server'
import { renderWithQuery } from '../test/render'
import { DashboardPage } from './DashboardPage'

// toHaveTextContent normalizes whitespace, so non-breaking spaces compare as plain ones
const SP = ' '
const NBSP = String.fromCharCode(160)

/** The hero and the cards have their data (the loading state has no test ids on purpose). */
async function loaded() {
  await screen.findByTestId('balance-hero')
}

function serve(patch: (base: Dashboard) => unknown) {
  server.use(http.get('*/v1/dashboard', () => HttpResponse.json(patch(dashboardA) as Record<string, unknown>)))
}

function figure(value: number, unit: Figure['unit'] = 'days'): Figure {
  return { value, unit, breakdown: [], source: ['bank'], note: 'Примечание.' }
}

describe('DashboardPage: loading and numbers', () => {
  it('shows the loading state first', () => {
    renderWithQuery(<DashboardPage />)

    expect(screen.getByRole('heading', { name: 'Рабочий стол' })).toBeInTheDocument()
    expect(screen.getByText('Загружаем Рабочий стол')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('balance-total')).not.toBeInTheDocument()
  })

  it('shows the balance, the three cards and the month with values from the API', async () => {
    renderWithQuery(<DashboardPage />)

    await loaded()
    expect(screen.getByTestId('dashboard')).toHaveAttribute('aria-busy', 'false')
    expect(screen.getByTestId('balance-total')).toHaveTextContent(`412${SP}800${SP}₽`)
    expect(screen.getByTestId('balance-bank')).toHaveTextContent(`341${SP}300${SP}₽`)
    expect(screen.getByTestId('balance-cash')).toHaveTextContent(`71${SP}500${SP}₽`)
    expect(screen.getByTestId('balance-runway')).toHaveTextContent(`Хватит на11${SP}дней`)
    expect(screen.getByTestId('balance-runway')).toHaveTextContent('при текущем темпе расходов')
    expect(screen.getByTestId('month-revenue')).toHaveTextContent(`330${SP}000${SP}₽`)
    expect(screen.getByTestId('month-expenses')).toHaveTextContent(`281${SP}000${SP}₽`)
    expect(screen.getByTestId('month-profit')).toHaveTextContent(`49${SP}000${SP}₽`)
    expect(screen.getByTestId('month-margin')).toHaveTextContent('рентабельность 14,8%')
    expect(screen.getByTestId('month-caption')).toHaveTextContent('Сентябрь · 9 дней из 30')
    expect(screen.getByTestId('dashboard-subtitle')).toHaveTextContent('9 сентября 2026 · данные обновлены в 04:12')
    expect(screen.getByRole('button', { name: `Остаток на счетах, 412${NBSP}800${NBSP}₽` })).toBeInTheDocument()
  })

  it('shows the week change in rubles and percent with a sign, as the API gave it (3,9%, not 3,8%)', async () => {
    renderWithQuery(<DashboardPage />)

    await loaded()
    const week = screen.getByTestId('balance-week-change')
    expect(week).toHaveTextContent(`+15${SP}400${SP}₽ · +3,9% за неделю`)
    expect(week).not.toHaveTextContent('3,8')
  })

  it('has no section for the month and no change line when the API leaves them out', async () => {
    serve((base) => {
      const { month, ...rest } = base
      void month // a response without the month block: the screen must not draw it
      return { ...rest, balance: { ...base.balance, week_change: null, week_change_pct: null } }
    })
    renderWithQuery(<DashboardPage />)

    await loaded()
    expect(screen.queryByTestId('month-caption')).not.toBeInTheDocument()
    expect(screen.queryByTestId('balance-week-change')).not.toBeInTheDocument()
  })

  it('says "без изменений за неделю" for a zero change', async () => {
    serve((base) => ({
      ...base,
      balance: {
        ...base.balance,
        week_change: { ...figure(0, 'rub'), delta: true },
        week_change_pct: { ...figure(0, 'pct'), delta: true },
      },
    }))
    renderWithQuery(<DashboardPage />)

    await loaded()
    expect(screen.getByTestId('balance-week-change')).toHaveTextContent('без изменений за неделю')
  })

  it('shows a decline with the real minus', async () => {
    serve((base) => ({
      ...base,
      balance: {
        ...base.balance,
        week_change: { ...figure(-320000, 'rub'), delta: true },
        week_change_pct: { ...figure(-2.1, 'pct'), delta: true },
      },
    }))
    renderWithQuery(<DashboardPage />)

    await loaded()
    expect(screen.getByTestId('balance-week-change')).toHaveTextContent(`−3${SP}200${SP}₽ · −2,1% за неделю`)
  })
})

describe('DashboardPage: tips', () => {
  it('opens the tip of the total with accounts, note and sources from the API', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()

    await user.click(within(screen.getByTestId('balance-total')).getByTestId('figure-tip-trigger'))

    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Расчётный счёт · Т-Банк 7972')
    expect(tip).toHaveTextContent('Касса клиники')
    expect(tip).toHaveTextContent(dashboardA.balance.total.note)
    expect(tip).toHaveTextContent('Банк')
    expect(tip).toHaveTextContent('Внесено вручную')
  })

  it('shows the week change tip with a signed value and the two balances', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()

    await user.click(within(screen.getByTestId('balance-week-change')).getAllByTestId('figure-tip-trigger')[0]!)

    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent(`+15${SP}400${SP}₽`)
    expect(tip).toHaveTextContent(`Расчётный счёт · Т-Банк 7972+14${SP}520${SP}₽`)
    expect(tip).toHaveTextContent(`Касса клиники+880${SP}₽`)
    expect(tip).toHaveTextContent(`Неделю назад (2 сентября)397${SP}400${SP}₽`)
    expect(tip).toHaveTextContent(`Сейчас412${SP}800${SP}₽`)
  })

  it('shows the runway tip with the formula note, and the revenue tip with reference rows', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()

    await user.click(within(screen.getByTestId('balance-runway')).getByTestId('figure-tip-trigger'))
    let tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent(`Расходы в день, в среднем37${SP}500${SP}₽`)
    expect(tip).toHaveTextContent('Платежи вперёд не учтены')

    await user.click(within(screen.getByTestId('month-revenue')).getByTestId('figure-tip-trigger'))
    tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Выручка · сентябрь')
    expect(screen.getAllByTestId('figure-tip-row')).toHaveLength(2)
    expect(screen.getAllByTestId('figure-tip-detail')).toHaveLength(2)
    expect(tip).toHaveTextContent(`Средний чек2${SP}142,86${SP}₽`)
    expect(tip).toHaveTextContent('Приёмов154')
  })

  it('gives every element with data-figure a tip trigger, and every tip a breakdown or a note, and a source', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()

    const marked = Array.from(document.querySelectorAll<HTMLElement>('[data-figure]'))
    expect(marked.length).toBeGreaterThanOrEqual(10)
    for (const element of marked) {
      const trigger = element.matches('[data-testid="figure-tip-trigger"]')
        ? element
        : element.querySelector<HTMLElement>('[data-testid="figure-tip-trigger"]')
      expect(trigger, `${element.getAttribute('data-figure')}: no tip trigger`).not.toBeNull()
    }
    for (const key of ['balance.total', 'balance.cash', 'balance.bank', 'balance.runway_days', 'month.revenue', 'month.expenses', 'month.profit', 'month.profit_margin_pct', 'balance.week_change', 'balance.week_change_pct']) {
      const element = document.querySelector<HTMLElement>(`[data-figure="${key}"]`)
      expect(element, key).not.toBeNull()
      await user.click(element!)
      expect(await screen.findByTestId('figure-tip'), key).toHaveTextContent('Источник:')
      expect(screen.getByTestId('figure-tip-source').textContent?.trim().length, key).toBeGreaterThan('Источник:'.length)
      await user.keyboard('{Escape}')
      await waitFor(() => expect(screen.queryByTestId('figure-tip')).not.toBeInTheDocument())
    }
  })

  it('leaves no sum or percent outside a tip trigger, a tip, an advice card or a marked counter', async () => {
    renderWithQuery(<DashboardPage />)
    await loaded()

    const amount = /\d[\d  ]*(?:[,.]\d+)?\s?(₽|%)/
    const offenders: string[] = []
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent ?? ''
      const parent = node.parentElement
      if (!parent || !amount.test(text)) continue
      if (parent.closest('[data-testid="figure-tip-trigger"], [data-testid="figure-tip"], [data-testid="advice-card"], [data-no-tip]')) continue
      offenders.push(text.trim())
    }
    expect(offenders).toEqual([])
  })

  it('does not show words of the cut scope', async () => {
    renderWithQuery(<DashboardPage />)
    await loaded()

    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/Ответ ИИ|только просмотр|филиал|нейросет/i)
    expect(text).not.toMatch(/(^|[^А-Яа-яЁё])ИИ([^А-Яа-яЁё]|$)/)
  })
})

describe('DashboardPage: chart', () => {
  it('draws 14 points with dates, an accessible name and a hidden table', async () => {
    renderWithQuery(<DashboardPage />)
    await loaded()

    const chart = screen.getByTestId('balance-trend')
    expect(chart).toHaveAttribute('aria-label', `График остатка за 14 дней: с 371${NBSP}200${NBSP}₽ до 412${NBSP}800${NBSP}₽`)
    const points = screen.getAllByTestId('balance-chart-point')
    expect(points).toHaveLength(14)
    expect(points[4]).toHaveAttribute('data-date', '2026-08-31')
    expect(within(chart).getAllByRole('row')).toHaveLength(15)
    expect(screen.getByText('Остаток на конец дня, 14 дней')).toBeInTheDocument()
  })

  it('is one Tab stop; arrows, Home and End move between days and open the tip of the day', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()
    const stops = () => within(screen.getByTestId('balance-trend')).getAllByRole('button').filter((b) => b.tabIndex === 0)
    expect(stops()).toHaveLength(1)
    expect(stops()[0]).toHaveAccessibleName(`9 сентября, 412${NBSP}800${NBSP}₽`)

    stops()[0]!.focus()
    expect(await screen.findByTestId('figure-tip')).toHaveTextContent('Остаток · 9 сентября')

    await user.keyboard('{ArrowLeft}')
    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Остаток · 8 сентября')
    expect(tip).toHaveTextContent(`408${SP}900${SP}₽`)
    expect(tip).toHaveTextContent('Остаток на конец дня по банку и кассе.')
    expect(stops()).toHaveLength(1)

    await user.keyboard('{Home}')
    expect(await screen.findByTestId('figure-tip')).toHaveTextContent('Остаток · 27 августа')
    await user.keyboard('{End}')
    expect(await screen.findByTestId('figure-tip')).toHaveTextContent('Остаток · 9 сентября')

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByTestId('figure-tip')).not.toBeInTheDocument())
    expect(document.activeElement).toBe(stops()[0])
  })

  it('draws a short series of three days and replaces a series of one with a text', async () => {
    setMockScenario('fewdata')
    renderWithQuery(<DashboardPage />)
    await loaded()
    expect(screen.getAllByTestId('balance-chart-point')).toHaveLength(3)
    expect(screen.getByText('Остаток на конец дня, 3 дня')).toBeInTheDocument()
  })

  it('shows a grey block with a text instead of the chart when the series is shorter than two points', async () => {
    serve((base) => ({ ...base, balance_trend: base.balance_trend?.slice(-1) }))
    renderWithQuery(<DashboardPage />)

    await loaded()
    expect(screen.getByTestId('balance-chart-empty')).toHaveTextContent('Динамика появится, когда накопится несколько дней данных.')
    expect(screen.queryByTestId('balance-trend')).not.toBeInTheDocument()
  })
})

describe('DashboardPage: advice', () => {
  it('lists the advice in the order of the API with severity words, and counts them', async () => {
    renderWithQuery(<DashboardPage />)
    await loaded()

    const cards = screen.getAllByTestId('advice-card')
    expect(cards.map((card) => card.getAttribute('data-advice-id'))).toEqual(dashboardA.advice?.map((item) => item.id))
    expect(cards.map((card) => card.getAttribute('data-severity'))).toEqual(['alert', 'warning', 'warning', 'good'])
    expect(within(cards[0]!).getByTestId('advice-severity')).toHaveTextContent('срочно')
    expect(within(cards[1]!).getByTestId('advice-severity')).toHaveTextContent('внимание')
    expect(within(cards[3]!).getByTestId('advice-severity')).toHaveTextContent('хорошо')
    expect(screen.getByRole('heading', { level: 2, name: 'Советы · 4' })).toBeInTheDocument()
    expect(within(cards[0]!).getByRole('heading', { level: 3 })).toHaveTextContent('Денег хватит на 11 дней')
  })

  it('opens "Почему?" with the summary, the steps and the sources, and closes it with "Свернуть"', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()
    const card = screen.getAllByTestId('advice-card')[0]!
    const button = within(card).getByTestId('advice-why')
    expect(button).toHaveTextContent('Почему?')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(within(card).queryByTestId('advice-why-body')).not.toBeInTheDocument()

    await user.click(button)

    expect(button).toHaveTextContent('Свернуть')
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const panel = within(card).getByTestId('advice-why-panel')
    expect(button).toHaveAttribute('aria-controls', panel.id)
    expect(panel).toHaveTextContent('Остаток делим на средний расход в день')
    expect(within(panel).getAllByTestId('advice-why-step')).toHaveLength(3)
    expect(within(panel).getByTestId('advice-why-sources')).toHaveTextContent('Источник: Банк и касса: остаток на 9 сентября; Операции банка и кассы за 28 дней')

    await user.click(button)
    expect(within(card).queryByTestId('advice-why-panel')).not.toBeInTheDocument()
    expect(button).toHaveTextContent('Почему?')
  })

  it('keeps one analysis open at a time and works from the keyboard', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()
    const [first, second] = screen.getAllByTestId('advice-card')

    within(first!).getByTestId('advice-why').focus()
    await user.keyboard('{Enter}')
    expect(within(first!).getByTestId('advice-why-panel')).toBeInTheDocument()

    await user.click(within(second!).getByTestId('advice-why'))
    expect(within(second!).getByTestId('advice-why-panel')).toBeInTheDocument()
    expect(within(first!).queryByTestId('advice-why-panel')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('advice-why-panel')).toHaveLength(1)
  })

  it('says everything is fine when the list is empty', async () => {
    setMockScenario('noadvice')
    renderWithQuery(<DashboardPage />)
    await loaded()

    const empty = screen.getByTestId('advice-empty')
    expect(empty).toHaveTextContent('Пока всё в порядке')
    expect(empty).toHaveTextContent('Заметных отклонений нет. Совет появится, если что-то выйдет из нормы.')
    expect(screen.queryByTestId('advice-why')).not.toBeInTheDocument()
  })

  it('explains an empty list by a short history', async () => {
    setMockScenario('fewdata')
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.getByTestId('advice-empty')).toHaveTextContent('Пока мало данных')
  })

  it('takes "not enough data" from advice_status, not from the length of the trend', async () => {
    serve((base) => ({ ...base, advice: [], advice_status: 'not_enough_data' }))
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.getByTestId('advice-empty')).toHaveTextContent('Пока мало данных')
  })

  it('draws no advice block when the response has no advice field', async () => {
    serve((base) => {
      const { advice, ...rest } = base
      void advice
      return rest
    })
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.queryByTestId('advice-section')).not.toBeInTheDocument()
  })
})

describe('DashboardPage: runway cases', () => {
  const withRunway = (runway: Figure | null | undefined) => (base: Dashboard): Dashboard => ({
    ...base,
    balance: { ...base.balance, runway_days: runway },
  })

  it('declines days: 1 день, 2 дня, 21 день', async () => {
    for (const [days, text] of [[1, '1 день'], [2, '2 дня'], [21, '21 день']] as const) {
      serve(withRunway(figure(days)))
      const { unmount } = renderWithQuery(<DashboardPage />)
      await loaded()
      expect(screen.getByTestId('balance-runway')).toHaveTextContent(text)
      unmount()
    }
  })

  it('says "больше года" above 365 days and keeps the exact number in the tip', async () => {
    const user = userEvent.setup()
    serve(withRunway(figure(412)))
    renderWithQuery(<DashboardPage />)
    await loaded()

    const card = screen.getByTestId('balance-runway')
    expect(card).toHaveTextContent('больше года')
    await user.click(within(card).getByTestId('figure-tip-trigger'))
    expect(await screen.findByTestId('figure-tip')).toHaveTextContent('412')
  })

  it('shows "0 дней" with the reason: empty accounts, below zero, or just a fast pace', async () => {
    setMockScenario('zero')
    const zero = renderWithQuery(<DashboardPage />)
    await loaded()
    expect(screen.getByTestId('balance-runway')).toHaveTextContent(`0${SP}дней`)
    expect(screen.getByTestId('balance-runway')).toHaveTextContent('на счетах пусто')
    zero.unmount()

    setMockScenario('negative')
    const negative = renderWithQuery(<DashboardPage />)
    await loaded()
    expect(screen.getByTestId('balance-runway')).toHaveTextContent('остаток ниже нуля')
    negative.unmount()

    serve(withRunway(figure(0)))
    renderWithQuery(<DashboardPage />)
    await loaded()
    expect(screen.getByTestId('balance-runway')).toHaveTextContent('при текущем темпе расходов')
  })

  it('shows a dash without a tip when the API has no runway', async () => {
    setMockScenario('norunway')
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.queryByTestId('balance-runway')).not.toBeInTheDocument()
    expect(screen.getByText('расходов пока нет')).toBeInTheDocument()
    expect(screen.getByText('Хватит на').closest('.kpi')?.querySelector('[data-testid="figure-tip-trigger"]')).toBeNull()
  })
})

describe('DashboardPage: states', () => {
  it('shows an error with a retry button, and retry loads the data', async () => {
    const user = userEvent.setup()
    setMockScenario('error')
    renderWithQuery(<DashboardPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не получилось загрузить Рабочий стол')
    expect(alert).toHaveTextContent('не загрузилось')
    expect(alert).toHaveTextContent('Это сбой на нашей стороне, ваши данные не пострадали. Попробуйте ещё раз.')
    expect(screen.getByTestId('dashboard-error')).toBeInTheDocument()

    setMockScenario('default')
    await user.click(screen.getByTestId('dashboard-error-retry'))

    await loaded()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('tells about a connection problem on network failure', async () => {
    setMockScenario('network')
    renderWithQuery(<DashboardPage />)

    expect(await screen.findByText('Нет связи с сервером. Проверьте интернет и повторите.')).toBeInTheDocument()
  })

  it('shows "no accounts" instead of the balance and the row, and still shows the month and advice blocks', async () => {
    setMockScenario('empty')
    renderWithQuery(<DashboardPage />)

    expect(await screen.findByText('Счетов пока нет')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-no-accounts')).toBeInTheDocument()
    expect(screen.queryByTestId('balance-hero')).not.toBeInTheDocument()
    expect(screen.queryByTestId('balance-total')).not.toBeInTheDocument()
    expect(screen.getByTestId('dashboard-subtitle')).toHaveTextContent('данные ещё не загружались')
    expect(screen.getByTestId('month-empty')).toBeInTheDocument()
    expect(screen.getByTestId('advice-empty')).toBeInTheDocument()
  })

  it('shows zero as a normal value with a hint', async () => {
    setMockScenario('zero')
    renderWithQuery(<DashboardPage />)

    await loaded()
    const total = screen.getByTestId('balance-total')
    expect(total).toHaveTextContent(`0${SP}₽`)
    expect(total).toHaveTextContent('на счетах пусто')
  })

  it('shows a negative balance with a minus sign and words', async () => {
    setMockScenario('negative')
    renderWithQuery(<DashboardPage />)

    await loaded()
    const total = screen.getByTestId('balance-total')
    expect(total).toHaveTextContent(`−12${SP}300${SP}₽`)
    expect(total).toHaveTextContent('ниже нуля')
    expect(screen.getByTestId('balance-bank')).toHaveTextContent('ниже нуля')
  })

  it('warns that the data is stale and links to the connections', async () => {
    setMockScenario('stale')
    renderWithQuery(<DashboardPage />)

    const banner = await screen.findByTestId('dashboard-stale-banner')
    expect(banner).toHaveTextContent('Данные обновлены вчера в 04:12 и могли устареть.')
    expect(within(banner).getByRole('link', { name: 'Проверить подключения' })).toHaveAttribute(
      'href',
      '/settings/connections/vetmanager',
    )
    expect(screen.getByTestId('balance-total')).toHaveTextContent(`412${SP}800${SP}₽`)
  })

  it('keeps old numbers and warns when a background refresh fails', async () => {
    const user = userEvent.setup()
    const { queryClient } = renderWithQuery(<DashboardPage />)
    await loaded()

    server.use(
      http.get('*/v1/dashboard', () => HttpResponse.json({ error: { code: 'sync_failed', message: 'x' } }, { status: 500 })),
    )
    await queryClient.invalidateQueries({ queryKey: ['dashboard'] })

    const banner = await screen.findByTestId('dashboard-refresh-banner')
    expect(banner).toHaveTextContent('Не удалось обновить. Показаны данные на 04:12.')
    expect(screen.getByTestId('balance-total')).toHaveTextContent(`412${SP}800${SP}₽`)

    server.resetHandlers()
    await user.click(within(banner).getByRole('button', { name: 'Обновить' }))
    await waitFor(() => expect(screen.queryByTestId('dashboard-refresh-banner')).not.toBeInTheDocument())
  })

  it('asks to load data when the month is empty, with links to the upload and the connections', async () => {
    setMockScenario('emptymonth')
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.getByTestId('month-caption')).toHaveTextContent(/^Сентябрь$/)
    const empty = screen.getByTestId('month-empty')
    expect(empty).toHaveTextContent('За сентябрь данных пока нет. Загрузите выписку или подключите Ветменеджер: цифры появятся здесь.')
    expect(within(empty).getByRole('link', { name: 'Загрузить выписку' })).toHaveAttribute('href', '/transactions?import=1')
    expect(within(empty).getByRole('link', { name: 'Подключения' })).toHaveAttribute('href', '/settings/connections/vetmanager')
    expect(screen.queryByTestId('month-revenue')).not.toBeInTheDocument()
  })

  it('says the month has just begun on its first day', async () => {
    serve((base) => (base.month ? { ...base, month: { ...base.month, days_passed: 0 } } : base))
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.getByTestId('month-caption')).toHaveTextContent('Сентябрь только начался')
    expect(screen.getByTestId('month-empty')).toBeInTheDocument()
  })

  it('shows 0 ₽ cards when the month has no revenue yet but data exists', async () => {
    serve((base) =>
      base.month ? { ...base, month: { ...base.month, revenue: { ...base.month.revenue, value: 0, breakdown: [] } } } : base,
    )
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.getByTestId('month-revenue')).toHaveTextContent(`0${SP}₽`)
  })
})

describe('DashboardPage: month sub-lines', () => {
  it('draws no forecast and no change to last month: the stage 2 contract does not send them', async () => {
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.queryByText(/прогноз месяца/)).not.toBeInTheDocument()
    expect(screen.queryByText(/к августу/)).not.toBeInTheDocument()
  })

  it('draws no margin line when the API leaves the margin out (no revenue)', async () => {
    serve((base) => {
      const { profit_margin_pct, ...month } = base.month
      void profit_margin_pct
      return { ...base, month }
    })
    renderWithQuery(<DashboardPage />)
    await loaded()

    expect(screen.getByTestId('month-profit')).toHaveTextContent(`49${SP}000${SP}₽`)
    expect(screen.queryByTestId('month-margin')).not.toBeInTheDocument()
  })
})

describe('DashboardPage: ?as_of=', () => {
  it('passes the date from the address to the API and shows it', async () => {
    let requested: string | null = null
    server.use(
      http.get('*/v1/dashboard', ({ request }) => {
        requested = new URL(request.url).searchParams.get('as_of')
        return HttpResponse.json({ ...dashboardA, as_of: requested ?? dashboardA.as_of })
      }),
    )
    renderWithQuery(<DashboardPage />, { path: '/?as_of=2026-09-10' })

    await loaded()
    expect(requested).toBe('2026-09-10')
    expect(screen.getByTestId('dashboard-subtitle')).toHaveTextContent('10 сентября 2026')
  })

  it('asks for today when the address has no date, or a wrong one', async () => {
    const seen: Array<string | null> = []
    server.use(
      http.get('*/v1/dashboard', ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('as_of'))
        return HttpResponse.json(dashboardA)
      }),
    )
    renderWithQuery(<DashboardPage />, { path: '/?as_of=tomorrow' })

    await loaded()
    expect(seen).toEqual([null])
  })
})
