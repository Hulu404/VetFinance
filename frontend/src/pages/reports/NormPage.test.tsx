import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { normExample } from '../../mocks/reportsFixtures'
import { setMockScenario } from '../../mocks/scenario'
import { renderWithQuery } from '../../test/render'
import { LocationProbe, numbersWithoutTip, stubWidth } from '../../test/reports'
import { NormPage } from './NormPage'

const NBSP = String.fromCharCode(160)
const MINUS = '−'
const KEYS = ['payroll', 'drugs', 'rent', 'lab', 'writeoff', 'acquiring', 'marketing', 'other', 'net_profit']

function renderNorm(path = '/reports/norm?month=2026-09') {
  return renderWithQuery(
    <>
      <NormPage />
      <LocationProbe />
    </>,
    { path, toasts: true },
  )
}

async function loaded() {
  await screen.findAllByTestId('norm-row')
}

const rowOf = (key: string) => document.querySelector(`[data-testid="norm-row"][data-key="${key}"]`) as HTMLElement

afterEach(() => vi.unstubAllGlobals())

describe('NormPage: the table', () => {
  it('shows the loading state first', () => {
    renderNorm()

    expect(screen.getByTestId('norm')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Загружаем отчёт')).toBeInTheDocument()
    expect(screen.getByTestId('norm-loading')).toBeInTheDocument()
    expect(screen.getByTestId('norm-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Норма')
  })

  it('lists the nine rows in order with status and tone of the API, and flags the memo row', async () => {
    renderNorm()
    await loaded()

    expect(screen.getAllByTestId('norm-row').map((row) => row.getAttribute('data-key'))).toEqual(KEYS)
    expect(rowOf('rent')).toHaveAttribute('data-status', 'above')
    expect(rowOf('rent')).toHaveAttribute('data-tone', 'bad')
    expect(rowOf('payroll')).toHaveAttribute('data-status', 'ok')
    expect(rowOf('payroll')).toHaveAttribute('data-tone', 'good')
    expect(rowOf('other')).toHaveAttribute('data-status', 'no_norm')
    expect(rowOf('net_profit')).toHaveAttribute('data-status', 'below')
    expect(rowOf('net_profit')).toHaveAttribute('data-tone', 'bad')
    expect(rowOf('writeoff')).toHaveAttribute('data-memo', 'true')
    expect(rowOf('writeoff')).toHaveTextContent('справочно, в сумму долей не входит')
    expect(rowOf('rent')).not.toHaveAttribute('data-memo')
    expect(screen.getByTestId('page-subtitle')).toHaveTextContent('Сентябрь 2026 · ваши показатели против нормы ветклиник на 2–6 врачей')
  })

  it('says the deviation in words, with the points, never by colour alone', async () => {
    renderNorm()
    await loaded()

    const pp = (key: string) => within(rowOf(key)).getByTestId('norm-deviation-pp')
    expect(pp('payroll').textContent).toBe('в норме')
    expect(pp('rent').textContent).toBe(`выше нормы на 0,1${NBSP}п.п.`)
    expect(pp('writeoff').textContent).toBe(`выше нормы на 1,9${NBSP}п.п.`)
    expect(pp('net_profit').textContent).toBe(`ниже нормы на 0,3${NBSP}п.п.`)
    expect(pp('rent').querySelector('.pill')).toHaveClass('pill--danger')
    expect(pp('payroll').querySelector('.pill')).toHaveClass('pill--success')
    expect(within(rowOf('other')).queryByTestId('norm-deviation-pp')).toHaveTextContent('—')
  })

  it('shows rubles with the sign, and a dash in the norm', async () => {
    renderNorm()
    await loaded()

    const rub = (key: string) => within(rowOf(key)).getByTestId('norm-deviation-rub')
    expect(rub('rent').textContent).toBe(`+1${NBSP}594,79${NBSP}₽`)
    expect(rub('net_profit').textContent).toBe(`${MINUS}3${NBSP}233,80${NBSP}₽`)
    expect(rub('payroll').textContent).toBe('—')
    expect(within(rub('payroll')).getByTestId('figure-tip-trigger')).toBeInTheDocument()
  })

  it('shows the norm corridor in a pill and the share of the revenue', async () => {
    renderNorm()
    await loaded()

    const norm = (key: string) => within(rowOf(key)).getByTestId('norm-norm')
    expect(norm('payroll').textContent).toBe('22–28%')
    expect(norm('writeoff').textContent).toBe(`до${NBSP}0,8%`)
    expect(norm('acquiring').textContent).toBe('1–2%')
    expect(within(rowOf('drugs')).getByTestId('norm-share')).toHaveTextContent('22,3%')
    expect(within(rowOf('other')).queryByTestId('norm-norm')).not.toBeInTheDocument()
    expect(rowOf('other')).toHaveTextContent('нормы нет')
  })

  it('opens the norm tip with the borders in rubles, the note and where the norm comes from', async () => {
    renderNorm()
    await loaded()

    within(within(rowOf('rent')).getByTestId('norm-norm')).getByTestId('figure-tip-trigger').focus()

    const tip = await screen.findByTestId('figure-tip')
    expect(within(tip).getAllByTestId('figure-tip-row')).toHaveLength(2)
    expect(tip).toHaveTextContent('5–10%')
    expect(tip).toHaveTextContent('Норма отрасли для ветклиник на 2–6 врачей.')
    expect(within(tip).getByTestId('figure-tip-source')).toHaveTextContent('Отраслевая норма')
  })

  it('gives every share, norm, deviation and rouble cell a data-figure path and a tip trigger', async () => {
    renderNorm()
    await loaded()

    for (const id of ['norm-norm', 'norm-share', 'norm-deviation-pp', 'norm-deviation-rub']) {
      const cells = screen.getAllByTestId(id).filter((cell) => cell.hasAttribute('data-figure'))
      expect(cells.length, id).toBeGreaterThan(0)
      for (const cell of cells) expect(within(cell).getByTestId('figure-tip-trigger')).toBeInTheDocument()
    }
    expect(within(rowOf('rent')).getByTestId('norm-share')).toHaveAttribute('data-figure', 'items.rent.actual_pct')
    expect(within(rowOf('rent')).getByTestId('norm-deviation-pp')).toHaveAttribute('data-figure', 'items.rent.deviation_pp')
  })

  it('draws a gauge with words for the screen reader on the rows that have a norm, and none for "Остальные статьи"', async () => {
    renderNorm()
    await loaded()

    expect(within(rowOf('rent')).getByRole('img', { name: `Норма 5–10%, у вас 10,1%: выше нормы на 0,1${NBSP}п.п.` })).toBeInTheDocument()
    expect(within(rowOf('payroll')).getByTestId('norm-gauge')).toHaveAttribute('aria-label', 'Норма 22–28%, у вас 23,9%: в норме')
    expect(within(rowOf('other')).queryByTestId('norm-gauge')).not.toBeInTheDocument()
  })

  it('leaves no sum or percent without a tip, and no forbidden words', async () => {
    renderNorm()
    await loaded()
    const main = screen.getByTestId('norm')

    expect(numbersWithoutTip(main)).toEqual([])
    expect(main.textContent?.toLowerCase()).not.toMatch(/\bии\b|роль|филиал|\bбот\b|катастроф|опасно/)
  })

  it('shows the headline from the API and the footnote', async () => {
    renderNorm()
    await loaded()

    expect(screen.getByTestId('norm-headline').textContent).toBe(normExample.headline)
    expect(screen.getByTestId('norm-footnote')).toHaveTextContent('Зелёная зона на шкале — норма отрасли, чёрточка — ваше значение.')
    expect(screen.getByTestId('norm-footnote')).toHaveTextContent('их сумма может отличаться от 100% на 0,1')
  })

  it('has a table on a wide screen', async () => {
    renderNorm()
    await loaded()

    expect(document.querySelectorAll('main table, table').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Статья',
      'Норма',
      'Где вы',
      'Ваша доля',
      'Отклонение',
      'В рублях',
    ])
  })
})

describe('NormPage: cards on 1100px and narrower', () => {
  it('replaces the table by a list of cards with the same cells', async () => {
    stubWidth(820)
    renderNorm()
    await loaded()

    expect(document.querySelector('table')).toBeNull()
    expect(screen.getAllByTestId('norm-row')).toHaveLength(9)
    const rent = rowOf('rent')
    expect(rent.tagName).toBe('LI')
    expect(within(rent).getByTestId('norm-gauge')).toBeInTheDocument()
    expect(within(rent).getByTestId('norm-share')).toHaveTextContent('10,1%')
    expect(within(rent).getByTestId('norm-norm')).toHaveTextContent('5–10%')
    expect(within(rent).getByTestId('norm-deviation-rub').textContent).toBe(`+1${NBSP}594,79${NBSP}₽`)
    expect(rent).toHaveTextContent('Ваша доля')
    expect(rent).toHaveTextContent('В рублях')
  })
})

describe('NormPage: states', () => {
  it('shows the empty card when there is no revenue', async () => {
    renderNorm('/reports/norm?month=2000-01')

    const empty = await screen.findByTestId('norm-empty')
    expect(empty).toHaveTextContent('За январь доли посчитать не из чего')
    expect(empty).toHaveTextContent('Нужна выручка за месяц. Подключите Ветменеджер или загрузите выписку: норма появится, когда данные будут.')
    expect(within(empty).getByRole('link', { name: 'Подключения' })).toBeInTheDocument()
    expect(screen.getByTestId('norm-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows the error card with Retry', async () => {
    const user = userEvent.setup()
    setMockScenario('error')
    renderNorm()

    const error = await screen.findByTestId('norm-error')
    expect(error).toHaveAttribute('role', 'alert')
    setMockScenario('default')
    await user.click(screen.getByTestId('norm-error-retry'))
    await loaded()
  })

  it('shows no verdicts in an open month: an info strip, no gauges, dashes, no status attributes', async () => {
    setMockScenario('reportopen')
    renderNorm('/reports/norm?month=2026-09')
    await loaded()

    expect(screen.getByTestId('norm-open-banner')).toHaveTextContent(
      'Месяц ещё идёт: доли считаются от неполной выручки, поэтому с нормой мы их пока не сравниваем. Сравнение появится, когда месяц закончится.',
    )
    expect(screen.getByTestId('norm-period-status')).toHaveTextContent('месяц идёт, данные по 9 сентября')
    expect(screen.getByTestId('norm-headline')).toHaveTextContent('К 9 сентября доли статей посчитаны от выручки за 9 дней. Сравним с нормой, когда месяц закончится.')
    expect(screen.queryByTestId('norm-gauge')).not.toBeInTheDocument()
    for (const row of screen.getAllByTestId('norm-row')) {
      expect(row).not.toHaveAttribute('data-status')
    }
    expect(within(rowOf('rent')).getByTestId('norm-deviation-pp').textContent).toBe('—')
    expect(within(rowOf('rent')).getByTestId('norm-deviation-rub').textContent).toBe('—')
    expect(within(rowOf('rent')).getByTestId('norm-norm').textContent).toBe('5–10%')
    expect(within(rowOf('rent')).getByTestId('norm-share')).toBeInTheDocument()
    expect(screen.getByTestId('norm').textContent).not.toMatch(/выше нормы|ниже нормы/)
  })

  it('tells "сравним после закрытия месяца" on the cards of an open month', async () => {
    setMockScenario('reportopen')
    stubWidth(390)
    renderNorm('/reports/norm?month=2026-09')
    await loaded()

    expect(rowOf('rent')).toHaveTextContent('сравним после закрытия месяца')
    expect(within(rowOf('rent')).queryByTestId('norm-gauge')).not.toBeInTheDocument()
  })

  it('shows the partial strips and "нормы нет" everywhere when there is no benchmark', async () => {
    setMockScenario('reportpartial')
    renderNorm()
    await loaded()

    const banners = screen.getAllByTestId('norm-partial-banner')
    expect(banners).toHaveLength(2)
    expect(banners[0]).toHaveTextContent('Нет данных Ветменеджера за сентябрь: доли считаются от неполной выручки.')
    expect(screen.queryByTestId('norm-gauge')).not.toBeInTheDocument()
    await waitFor(() => expect(rowOf('rent')).toHaveTextContent('нормы нет'))
    expect(rowOf('rent')).toHaveAttribute('data-status', 'no_norm')
    expect(screen.getByTestId('norm-headline')).toHaveTextContent('Нормы для вашей клиники пока нет, но доли статей ниже.')
  })

  it('writes the month the API chose into the address and moves between months', async () => {
    const user = userEvent.setup()
    renderNorm('/reports/norm')

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-09'))
    await loaded()
    await user.click(screen.getByTestId('norm-month-prev'))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-08'))
  })

  it('shows the stale-data strip', async () => {
    setMockScenario('stale')
    renderNorm()
    await loaded()

    expect(await screen.findByTestId('norm-stale-banner')).toHaveTextContent('могли устареть')
  })
})
