import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { setMockScenario } from '../../mocks/scenario'
import { renderWithQuery } from '../../test/render'
import { LocationProbe, numbersWithoutTip } from '../../test/reports'
import { EfficiencyPage } from './EfficiencyPage'

function renderEfficiency(path = '/analytics/efficiency') {
  return renderWithQuery(
    <>
      <EfficiencyPage />
      <LocationProbe />
    </>,
    { path, toasts: true },
  )
}

describe('EfficiencyPage: rooms', () => {
  it('shows the loading state, then the headline, the cards and the rooms', async () => {
    renderEfficiency()
    expect(screen.getByTestId('efficiency')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Загружаем данные')).toBeInTheDocument()
    await screen.findByTestId('efficiency-headline')
    expect(screen.getByTestId('efficiency')).toHaveAttribute('data-load-by', 'rooms')
    expect(screen.getByRole('heading', { name: 'Загрузка по кабинетам' })).toBeInTheDocument()
    const rows = screen.getAllByTestId('efficiency-load-row')
    expect(rows.length).toBeGreaterThan(0)
    expect(rows[0]).toHaveAttribute('data-kind', 'room')
    expect(within(rows[0] as HTMLElement).getByTestId('efficiency-load-pct')).toHaveTextContent(/из .* ч · свободно .* ч/)
    expect(screen.getAllByTestId('efficiency-part').map((part) => part.getAttribute('data-key'))).toEqual(['hours', 'busy_hours', 'fixed', 'obligations'])
    expect(screen.getByTestId('efficiency-hour-margin')).toBeInTheDocument()
    expect(screen.queryByTestId('efficiency-hours-open')).not.toBeInTheDocument()
  })

  it('has no number without a tip', async () => {
    renderEfficiency()
    await screen.findByTestId('efficiency-headline')
    expect(numbersWithoutTip(screen.getByTestId('efficiency'))).toEqual([])
  })

  it('writes the month of the answer into the address and disables the next month on the last closed one', async () => {
    renderEfficiency()
    await screen.findByTestId('efficiency-headline')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-09'))
    expect(screen.getByTestId('efficiency-month-next')).toHaveAttribute('aria-disabled', 'true')
    expect(await screen.findByTestId('efficiency-period-status')).toHaveTextContent('месяц закрыт')
  })

  it('replaces a month later than the closed one with the last closed month', async () => {
    renderEfficiency('/analytics/efficiency?month=2999-01')
    await screen.findByTestId('efficiency-headline')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('month=2026-09'))
  })
})

describe('EfficiencyPage: doctors (the fallback mode)', () => {
  it('shows doctors, the note and the button of the hours, without errors', async () => {
    setMockScenario('effward')
    renderEfficiency()
    await screen.findByTestId('efficiency-headline')
    expect(screen.getByTestId('efficiency')).toHaveAttribute('data-load-by', 'doctors')
    expect(screen.getByRole('heading', { name: 'Загрузка по врачам' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Стоимость часа приёма' })).toBeInTheDocument()
    expect(screen.getByTestId('efficiency-fallback-note')).toHaveTextContent('Расписания кабинетов нет, поэтому считаем по часам приёма врачей')
    expect(screen.getByTestId('efficiency-hours-open')).toHaveTextContent('Изменить часы приёма')
    expect(screen.queryByTestId('efficiency-error')).not.toBeInTheDocument()
  })

  it('shows the banner and dashes when no hours are set, and the hours are saved from the dialog', async () => {
    setMockScenario('effnohours')
    const user = userEvent.setup()
    renderEfficiency()
    const banner = await screen.findByTestId('efficiency-hours-banner')
    expect(banner).toHaveTextContent('Загрузку и стоимость часа посчитать нельзя: не указаны часы приёма врачей.')
    expect(screen.getByTestId('efficiency-load')).toHaveTextContent('—')
    expect(screen.getByTestId('efficiency-hour-cost')).toHaveTextContent('—')
    expect(screen.getByTestId('efficiency-visits')).not.toHaveTextContent('—')
    expect(screen.getAllByTestId('efficiency-no-hours').length).toBeGreaterThan(0)

    await user.click(within(banner).getByRole('button', { name: 'Указать часы приёма' }))
    const dialog = await screen.findByTestId('efficiency-hours-dialog')
    const fields = await within(dialog).findAllByTestId(/^efficiency-hours-field-doctor-[^-]+(-[^-]+)*$/)
    for (const field of fields) await user.type(field, '30')
    await user.click(within(dialog).getByTestId('efficiency-hours-save'))
    expect(await screen.findByText('Часы приёма сохранены')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByTestId('efficiency-hours-banner')).not.toBeInTheDocument())
  })

  it('names the mistakes of the hours form', async () => {
    setMockScenario('effward')
    const user = userEvent.setup()
    renderEfficiency()
    await user.click(await screen.findByTestId('efficiency-hours-open'))
    const dialog = await screen.findByTestId('efficiency-hours-dialog')
    const minutes = await within(dialog).findByTestId('efficiency-hours-field-minutes')
    await user.clear(minutes)
    await user.type(minutes, '1')
    await user.click(within(dialog).getByTestId('efficiency-hours-save'))
    expect(await within(dialog).findByTestId('efficiency-hours-field-minutes-error')).toHaveTextContent('От 5 до 240 минут')
  })
})

describe('EfficiencyPage: other states', () => {
  it('asks to load the statement when there are no expenses', async () => {
    setMockScenario('effnoexpenses')
    renderEfficiency()
    const banner = await screen.findByTestId('efficiency-expenses-banner')
    expect(banner).toHaveTextContent('стоимость часа посчитать нельзя. Загрузите выписку.')
    expect(screen.getByTestId('efficiency-hour-cost')).toHaveTextContent('—')
  })

  it('shows the empty state', async () => {
    setMockScenario('effempty')
    renderEfficiency()
    expect(await screen.findByTestId('efficiency-empty')).toHaveTextContent('Загрузите продажи из Ветменеджера')
  })

  it('shows the error with a retry', async () => {
    setMockScenario('efferror')
    renderEfficiency()
    expect(await screen.findByTestId('efficiency-error')).toHaveTextContent('Не получилось загрузить данные')
    expect(screen.getByTestId('efficiency-error-retry')).toBeInTheDocument()
  })

  it('shows the stale-data strip when the dashboard says so', async () => {
    setMockScenario('stale')
    renderEfficiency()
    expect(await screen.findByTestId('efficiency-stale-banner')).toBeInTheDocument()
  })
})
