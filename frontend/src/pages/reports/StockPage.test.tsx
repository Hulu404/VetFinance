import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StockIdleItem, StockReport } from '../../api/types'
import { stockExample, stockIdleExample } from '../../mocks/reportsFixtures'
import { setMockScenario } from '../../mocks/scenario'
import { server } from '../../mocks/server'
import { renderWithQuery } from '../../test/render'
import { LocationProbe, numbersWithoutTip, stubWidth } from '../../test/reports'
import { StockPage } from './StockPage'

const NBSP = String.fromCharCode(160)

function renderStock(path = '/reports/stock') {
  return renderWithQuery(
    <>
      <StockPage />
      <LocationProbe />
    </>,
    { path, toasts: true },
  )
}

async function loaded() {
  await screen.findByTestId('stock-frozen')
}

function serveStock(patch: (base: StockReport) => StockReport) {
  server.use(http.get('*/v1/reports/stock', () => HttpResponse.json(patch(stockExample) as unknown as Record<string, unknown>)))
}

function manyIdle(count: number): StockIdleItem[] {
  const template = stockIdleExample.items[0] as StockIdleItem
  return Array.from({ length: count }, (_, index) => ({ ...template, item: `Позиция ${index + 1}`, last_movement_on: '2026-03-15' }))
}

afterEach(() => vi.unstubAllGlobals())

describe('StockPage: cards and the lists', () => {
  it('shows the loading state first with a hidden status text and a disabled export', () => {
    renderStock()

    expect(screen.getByTestId('stock')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Загружаем склад')).toBeInTheDocument()
    expect(screen.getByTestId('stock-loading')).toBeInTheDocument()
    expect(screen.getByTestId('stock-export-pdf')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByTestId('stock-frozen')).not.toBeInTheDocument()
  })

  it('shows the three cards with the figures of the API and the sub-lines with their own tips', async () => {
    renderStock()
    await loaded()

    expect(screen.getByTestId('stock-frozen').textContent).toBe(`378${NBSP}270${NBSP}₽`)
    expect(screen.getByTestId('stock-expiring').textContent).toBe(`92${NBSP}928,50${NBSP}₽`)
    expect(screen.getByTestId('stock-written-off').textContent).toBe(`34${NBSP}100${NBSP}₽`)
    expect(screen.getByTestId('stock-frozen-positions')).toHaveTextContent('6 позиций')
    expect(screen.getByTestId('stock-written-off-norm').textContent).toBe(`норма — до 8${NBSP}785,25${NBSP}₽`)
    expect(screen.getByText('Списано в сентябре')).toBeInTheDocument()
    expect(screen.getByText('Срок истекает за 60 дней')).toBeInTheDocument()
    expect(screen.getByText('Без движения от 60 дней')).toBeInTheDocument()
    expect(screen.getByTestId('stock-expiring').closest('.stock-card')).toHaveTextContent('7 партий')
    expect(screen.queryByTestId('stock-expiring-risk')).not.toBeInTheDocument()
  })

  it('opens the frozen tip with the three age buckets', async () => {
    renderStock()
    await loaded()

    within(screen.getByTestId('stock-frozen')).getByTestId('figure-tip-trigger').focus()

    const tip = await screen.findByTestId('figure-tip')
    expect(within(tip).getAllByTestId('figure-tip-row')).toHaveLength(3)
    expect(tip).toHaveTextContent('Без движения 60–89 дней')
    expect(within(tip).getByTestId('figure-tip-source')).toHaveTextContent('Ветменеджер')
  })

  it('shows the subtitle with the date of the balances and the headline of the API', async () => {
    renderStock()
    await loaded()

    expect(screen.getByTestId('page-subtitle')).toHaveTextContent('Остатки на утро 30 сентября 2026 · данные склада из Ветменеджера')
    expect(screen.getByTestId('stock-headline')).toHaveTextContent('Срок годности истекает у 7 партий на 92 928,50 ₽.')
  })

  it('puts the expired batches in a strip of their own, with the sum as a tip button', async () => {
    renderStock()
    await loaded()

    const banner = screen.getByTestId('stock-expired-banner')
    expect(banner).toHaveTextContent('На полке лежат партии с истёкшим сроком: 555 ₽. Их стоит списать.')
    expect(within(banner).getByTestId('stock-expired')).toHaveAttribute('data-figure', 'expired_on_hand')
    expect(within(banner).getByTestId('figure-tip-trigger')).toBeInTheDocument()
    const items = screen.getAllByTestId('stock-expiring-row').map((row) => row.getAttribute('data-item'))
    expect(items).not.toContain('Цефтриаксон, флакон')
  })

  it('lists the expiring batches in the order of the API with days left and amounts', async () => {
    renderStock()
    await loaded()

    const rows = screen.getAllByTestId('stock-expiring-row')
    expect(rows.map((row) => row.getAttribute('data-item'))).toEqual(stockExample.expiring.map((row) => row.item))
    expect(rows.map((row) => Number(row.getAttribute('data-days-left')))).toEqual(stockExample.expiring.map((row) => row.days_left))
    expect(within(rows[0] as HTMLElement).getByText('сегодня')).toBeInTheDocument()
    expect(within(rows[1] as HTMLElement).getByText('1 день')).toBeInTheDocument()
    expect(within(rows[2] as HTMLElement).getByText(/^24\s+дня$/)).toBeInTheDocument()
    expect(within(rows[0] as HTMLElement).getByTestId('stock-expiring-amount').textContent).toBe(`1${NBSP}560${NBSP}₽`)
    expect(within(rows[0] as HTMLElement).getByTestId('stock-expiring-amount')).toHaveAttribute('data-figure', 'expiring.0.amount')
    expect(screen.queryByText('Успеем израсходовать?')).not.toBeInTheDocument()
    expect(rows[2]).toHaveTextContent('до 24 октября')
  })

  it('adds the column "Успеем израсходовать?" once the API gives the risk of a batch', async () => {
    serveStock((base) => ({
      ...base,
      expiring: base.expiring.map((row, index) =>
        index === 2 ? { ...row, at_risk: { qty: 7, amount: row.amount } } : { ...row, at_risk: null },
      ),
    }))
    renderStock()
    await loaded()

    expect(screen.getByText('Успеем израсходовать?')).toBeInTheDocument()
    const rows = screen.getAllByTestId('stock-expiring-row')
    expect(rows[0]).toHaveTextContent('да')
    expect(rows[2]).toHaveTextContent('нет: может уйти в списание 7 ед. на')
    expect(within(rows[2] as HTMLElement).getByTestId('stock-expiring-risk-cell')).toHaveAttribute('data-figure', 'expiring.2.at_risk')
  })

  it('shows the turnover with its tip and the norm', async () => {
    renderStock()
    await loaded()

    expect(screen.getByTestId('stock-turnover').textContent).toBe(`59${NBSP}дней`)
    expect(screen.getByTestId('stock-norm-turnover')).toHaveTextContent('45 дней')
    within(screen.getByTestId('stock-turnover')).getByTestId('figure-tip-trigger').focus()
    const tip = await screen.findByTestId('figure-tip')
    expect(within(tip).getAllByTestId('figure-tip-row')).toHaveLength(3)
    expect(tip).toHaveTextContent('Окно расчёта')
  })

  it('lists the write-offs of the month with the reason in words', async () => {
    renderStock()
    await loaded()

    const rows = screen.getAllByTestId('stock-writeoff-row')
    expect(rows).toHaveLength(5)
    expect(rows[0]).toHaveTextContent('Вакцина Нобивак DHPPi, доза')
    expect(rows[0]).toHaveTextContent('17 сентября')
    expect(rows[0]).toHaveTextContent('истёк срок годности')
    expect(rows[3]).toHaveTextContent('порча или брак')
    expect(within(rows[0] as HTMLElement).getByTestId('stock-writeoff-amount')).toHaveAttribute('data-figure', 'written_off_items.0.amount')
    expect(screen.getByText('Что списали в сентябре')).toBeInTheDocument()
  })

  it('leaves no sum or percent without a tip', async () => {
    renderStock()
    await loaded()
    await screen.findAllByTestId('stock-idle-row')

    expect(numbersWithoutTip(screen.getByTestId('stock'))).toEqual([])
  })

  it('has no forbidden words', async () => {
    renderStock()
    await loaded()

    expect(screen.getByTestId('stock').textContent?.toLowerCase()).not.toMatch(/сгорит|потеряете|\bии\b|филиал|\bбот\b/)
  })
})

describe('StockPage: "Товары без движения"', () => {
  it('shows tabs with counts, the first list and keeps the interval in the address', async () => {
    const user = userEvent.setup()
    renderStock()
    await loaded()

    const tabs = await screen.findAllByTestId('stock-idle-tab')
    expect(tabs.map((tab) => tab.getAttribute('data-bucket'))).toEqual(['all', '60_89', '90_179', '180_plus'])
    expect(screen.getByRole('tab', { name: '60–89 дней, 2' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Все от 60 дней, 6' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findAllByTestId('stock-idle-row')).toHaveLength(6)

    await user.click(screen.getByRole('tab', { name: 'От 180 дней, 2' }))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('idle=180'))
    await waitFor(() => expect(screen.getAllByTestId('stock-idle-row')).toHaveLength(2))
    expect(screen.getByRole('tab', { name: 'От 180 дней, 2' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', screen.getByRole('tab', { name: 'От 180 дней, 2' }).id)
  })

  it('starts on the interval named in the address', async () => {
    renderStock('/reports/stock?idle=90')
    await loaded()

    await waitFor(() => expect(screen.getAllByTestId('stock-idle-row')).toHaveLength(2))
    expect(screen.getByRole('tab', { name: '90–179 дней, 2' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the last movement, days without movement and the amount with a tip', async () => {
    renderStock()
    await loaded()

    const row = (await screen.findAllByTestId('stock-idle-row'))[0] as HTMLElement
    expect(row).toHaveTextContent('Рентген-плёнка 35x43')
    expect(row).toHaveTextContent('15 марта')
    expect(row).toHaveTextContent('199')
    expect(within(row).getByTestId('stock-idle-amount').textContent).toBe(`148${NBSP}000${NBSP}₽`)
    expect(within(row).getByTestId('stock-idle-amount')).toHaveAttribute('data-figure', 'idle.items.0.amount')
    expect(within(row).getByTestId('figure-tip-trigger')).toBeInTheDocument()
  })

  it('loads the next ten with "Показать ещё" and keeps the note about the Excel file', async () => {
    const user = userEvent.setup()
    const all = manyIdle(12)
    server.use(
      http.get('*/v1/reports/stock/idle', ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get('cursor') ?? 0)
        const items = all.slice(offset, offset + 10)
        return HttpResponse.json({
          items,
          next_cursor: offset + 10 < all.length ? String(offset + 10) : null,
          total: stockIdleExample.total,
        } as unknown as Record<string, unknown>)
      }),
    )
    renderStock()
    await loaded()

    expect(await screen.findAllByTestId('stock-idle-row')).toHaveLength(10)
    expect(screen.getByText(/Показаны 10 позиций с наибольшей суммой\. Полный список — в файле Excel\./)).toBeInTheDocument()

    await user.click(screen.getByTestId('stock-idle-more'))

    await waitFor(() => expect(screen.getAllByTestId('stock-idle-row')).toHaveLength(12))
    expect(screen.queryByTestId('stock-idle-more')).not.toBeInTheDocument()
  })

  it('says so when an interval has no items, and when nothing is idle at all', async () => {
    server.use(http.get('*/v1/reports/stock/idle', () => HttpResponse.json({ items: [], next_cursor: null, total: stockIdleExample.total } as unknown as Record<string, unknown>)))
    renderStock('/reports/stock?idle=60')
    await loaded()

    expect(await screen.findByText('В этом интервале товаров нет.')).toBeInTheDocument()
  })

  it('shows an error inside the block and loads the list again on Retry, the other blocks stay', async () => {
    const user = userEvent.setup()
    server.use(http.get('*/v1/reports/stock/idle', () => HttpResponse.json({ error: { code: 'sync_failed', message: 'x', details: {} } }, { status: 500 })))
    renderStock()
    await loaded()

    const error = await screen.findByTestId('stock-idle-error')
    expect(error).toHaveTextContent('Не получилось загрузить список.')
    expect(screen.getAllByTestId('stock-writeoff-row').length).toBeGreaterThan(0)

    server.resetHandlers()
    await user.click(within(error).getByRole('button', { name: 'Повторить' }))
    expect(await screen.findAllByTestId('stock-idle-row')).toHaveLength(6)
  })

  it('passes as_of to both requests', async () => {
    const asked: string[] = []
    server.events.on('request:start', ({ request }) => asked.push(request.url))
    renderStock('/reports/stock?as_of=2026-09-30')
    await loaded()
    await screen.findAllByTestId('stock-idle-row')

    expect(asked.filter((url) => url.includes('/v1/reports/stock')).every((url) => url.includes('as_of=2026-09-30'))).toBe(true)
    server.events.removeAllListeners()
  })
})

describe('StockPage: states', () => {
  it('shows the empty card without a button before the loader of the warehouse exists', async () => {
    setMockScenario('reportempty')
    renderStock()

    const empty = await screen.findByTestId('stock-empty')
    expect(empty).toHaveTextContent('Данных склада пока нет')
    expect(empty).toHaveTextContent('Остатки и сроки годности появятся, когда заработает загрузка склада из Ветменеджера.')
    expect(within(empty).queryByRole('link')).not.toBeInTheDocument()
    expect(within(empty).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByTestId('stock-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByTestId('stock-frozen')).not.toBeInTheDocument()
  })

  it('shows calm texts in empty blocks, without cheering', async () => {
    setMockScenario('reportcalm')
    renderStock()
    await loaded()

    expect(screen.getByTestId('stock-frozen').textContent).toBe(`0${NBSP}₽`)
    expect(screen.getByText('всё в обороте')).toBeInTheDocument()
    expect(screen.getByText('сроки не истекают')).toBeInTheDocument()
    expect(screen.getByText('В ближайшие 60 дней сроки годности не истекают.')).toBeInTheDocument()
    expect(await screen.findByText('Товаров без движения дольше 60 дней нет.')).toBeInTheDocument()
    expect(screen.getByText('В сентябре списаний не было.')).toBeInTheDocument()
    expect(screen.queryByTestId('stock-expired-banner')).not.toBeInTheDocument()
    expect(screen.getByTestId('stock').textContent).not.toMatch(/отлично|идеально/)
  })

  it('shows the error card with Retry', async () => {
    const user = userEvent.setup()
    setMockScenario('error')
    renderStock()

    const error = await screen.findByTestId('stock-error')
    expect(error).toHaveTextContent('Не получилось загрузить склад')
    expect(error).toHaveAttribute('role', 'alert')
    setMockScenario('default')
    await user.click(screen.getByTestId('stock-error-retry'))
    await loaded()
  })

  it('shows the three reasons of partial data, the count of batches without expiry from the API', async () => {
    setMockScenario('reportpartial')
    renderStock()
    await loaded()

    const banners = screen.getAllByTestId('stock-partial-banner')
    expect(banners).toHaveLength(2)
    expect(banners[0]).toHaveTextContent('У 14 партий не указан срок годности: они не попали в список сроков.')
    expect(banners[1]).toHaveTextContent('Расход считаем меньше чем за 90 дней: риск списания приблизительный.')
  })

  it('shows the stale-data strip', async () => {
    setMockScenario('stale')
    renderStock()
    await loaded()

    expect(await screen.findByTestId('stock-stale-banner')).toHaveTextContent('могли устареть')
  })
})

describe('StockPage: cards on narrow screens', () => {
  it('turns the tables into lists with the same test ids', async () => {
    stubWidth(390)
    renderStock()
    await loaded()
    await screen.findAllByTestId('stock-idle-row')

    expect(document.querySelector('table')).toBeNull()
    expect(screen.getAllByTestId('stock-expiring-row')).toHaveLength(7)
    expect(screen.getAllByTestId('stock-writeoff-row')).toHaveLength(5)
    expect(screen.getAllByTestId('stock-idle-row')).toHaveLength(6)
    expect(screen.getAllByTestId('stock-expiring-amount')).toHaveLength(7)
  })
})
