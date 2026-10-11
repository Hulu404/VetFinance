import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../mocks/server'
import { dashboardA } from '../mocks/fixtures'
import { setMockScenario } from '../mocks/scenario'
import { renderWithQuery } from '../test/render'
import { DashboardPage } from './DashboardPage'

// toHaveTextContent normalizes whitespace: non-breaking spaces compare as plain ones
const SP = ' '
const NBSP = String.fromCharCode(160)

/** Both cards have their data (the loading state has no test ids on purpose). */
async function loaded() {
  await screen.findAllByTestId('figure-tip-trigger')
}

describe('DashboardPage', () => {
  it('shows the loading state first', () => {
    renderWithQuery(<DashboardPage />)

    expect(screen.getByRole('heading', { name: 'Рабочий стол' })).toBeInTheDocument()
    expect(screen.getByText('Загружаем остаток')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Остаток на счетах' })).toHaveAttribute('aria-busy', 'true')
  })

  it('shows balance cards with values from the API (golden set01, clinic A)', async () => {
    renderWithQuery(<DashboardPage />)

    await loaded()
    const total = screen.getByTestId('balance-total')
    expect(total).toHaveTextContent(`2${SP}282${SP}658,55${SP}₽`)
    expect(screen.getByTestId('balance-bank')).toHaveTextContent(`2${SP}149${SP}716,25${SP}₽`)
    expect(await screen.findByText('9 сентября 2026 · данные обновлены в 04:12')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: `Остаток на счетах, 2${NBSP}282${NBSP}658,55${NBSP}₽` })).toBeInTheDocument()
  })

  it('opens the tip on the total card with accounts, note and sources from the API', async () => {
    const user = userEvent.setup()
    renderWithQuery(<DashboardPage />)
    await loaded()
    const card = screen.getByTestId('balance-total')

    await user.click(within(card).getByTestId('figure-tip-trigger'))

    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Расчётный счёт')
    expect(tip).toHaveTextContent('Резервный счёт')
    expect(tip).toHaveTextContent('Касса')
    expect(tip).toHaveTextContent(dashboardA.balance.total.note)
    expect(tip).toHaveTextContent('Банк')
    expect(tip).toHaveTextContent('Ветменеджер')
    expect(tip).toHaveTextContent('Внесено вручную')
  })

  it('shows an error with a retry button, and retry loads the data', async () => {
    const user = userEvent.setup()
    setMockScenario('error')
    renderWithQuery(<DashboardPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не получилось загрузить остаток')
    expect(alert).toHaveTextContent('не загрузилось')

    setMockScenario('default')
    await user.click(screen.getByRole('button', { name: 'Повторить' }))

    await loaded()
    expect(screen.getByTestId('balance-total')).toHaveTextContent('₽')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('tells about a connection problem on network failure', async () => {
    setMockScenario('network')
    renderWithQuery(<DashboardPage />)

    expect(await screen.findByText('Нет связи с сервером. Проверьте интернет и повторите.')).toBeInTheDocument()
  })

  it('shows "no accounts" when the breakdown is empty', async () => {
    setMockScenario('empty')
    renderWithQuery(<DashboardPage />)

    expect(await screen.findByText('Счетов пока нет')).toBeInTheDocument()
    expect(screen.queryByTestId('balance-total')).not.toBeInTheDocument()
    expect(screen.getByText('данные ещё не загружались', { exact: false })).toBeInTheDocument()
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
  })

  it('keeps old numbers and warns when a background refresh fails', async () => {
    const { queryClient } = renderWithQuery(<DashboardPage />)
    await loaded()

    server.use(
      http.get('*/v1/dashboard', () =>
        HttpResponse.json({ error: { code: 'sync_failed', message: 'x' } }, { status: 500 }),
      ),
    )
    await queryClient.invalidateQueries({ queryKey: ['dashboard'] })

    expect(await screen.findByText('не удалось обновить')).toBeInTheDocument()
    expect(screen.getByText('Показаны данные на 04:12')).toBeInTheDocument()
    expect(screen.getByTestId('balance-total')).toHaveTextContent(`2${SP}282${SP}658,55${SP}₽`)
    expect(screen.getByRole('button', { name: 'Обновить' })).toBeInTheDocument()
  })
})
