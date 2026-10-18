import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { setMockScenario } from '../../mocks/scenario'
import { renderWithQuery } from '../../test/render'
import { LocationProbe, numbersWithoutTip } from '../../test/reports'
import { PricePage } from './PricePage'

const COT = '670666eb-c214-5d6b-865d-927f027d2c50'
const NO_RECIPE = '71293917-975f-5e89-9069-0ff8bcc42a69'
const WARD = 'a96655c3-4d6b-564c-bdad-37c1f034db0c'

function renderPrice(path = '/price') {
  return renderWithQuery(
    <>
      <PricePage />
      <LocationProbe />
    </>,
    { path, toasts: true },
  )
}

const loaded = () => screen.findAllByTestId('price-row')

describe('PricePage: the list', () => {
  it('shows the loading state, then the headline of the API and the worst margin first', async () => {
    renderPrice()
    expect(screen.getByTestId('price')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Загружаем прайс')).toBeInTheDocument()
    const rows = await loaded()
    expect(screen.getByTestId('price-headline')).toHaveTextContent('Сильнее всего «Стационар, сутки»')
    expect(rows[0]).toHaveAttribute('data-id', WARD)
    expect(rows[0]).toHaveAttribute('data-loss', 'true')
    expect(within(rows[0] as HTMLElement).getByTestId('price-row-pill')).toHaveAttribute('data-kind', 'loss')
    expect(screen.getByTestId('price-sort-margin')).toHaveAttribute('aria-sort', 'ascending')
    expect(screen.getByTestId('price-filter-no-recipe')).toHaveAttribute('data-count', '2')
  })

  it('has no number without a tip in the list', async () => {
    renderPrice()
    await loaded()
    expect(numbersWithoutTip(screen.getByTestId('price-table'))).toEqual([])
  })

  it('shows a dash instead of the margin of a service without a recipe', async () => {
    renderPrice()
    await loaded()
    const row = document.querySelector(`[data-testid="price-row"][data-id="${NO_RECIPE}"]`) as HTMLElement
    expect(row).toHaveAttribute('data-status', 'no_recipe')
    expect(within(row).getByTestId('price-row-margin')).toHaveTextContent('—')
    expect(within(row).getByTestId('price-row-pill')).toHaveTextContent('нет техкарты')
  })

  it('filters the list on the server and writes the filter into the address', async () => {
    const user = userEvent.setup()
    renderPrice()
    await loaded()
    await user.click(screen.getByTestId('price-filter-loss'))
    await waitFor(() => expect(screen.getAllByTestId('price-row')).toHaveLength(1))
    expect(screen.getByTestId('location')).toHaveTextContent('filter=loss')
  })

  it('tells when nothing is found', async () => {
    renderPrice('/price?q=нет-такой')
    expect(await screen.findByTestId('price-empty-filter')).toHaveTextContent('Ничего не нашли. Проверьте название.')
  })

  it('shows the empty state without services', async () => {
    setMockScenario('priceempty')
    renderPrice()
    expect(await screen.findByTestId('price-empty')).toHaveTextContent('Услуг пока нет')
  })

  it('shows the error with a retry', async () => {
    setMockScenario('priceerror')
    renderPrice()
    expect(await screen.findByTestId('price-error')).toHaveTextContent('Не получилось загрузить прайс')
    expect(screen.getByTestId('price-error-retry')).toBeInTheDocument()
  })
})

describe('PricePage: the card', () => {
  it('opens the card with the eight parts of the price and a tip on each', async () => {
    renderPrice(`/price?service=${COT}`)
    const card = await screen.findByTestId('price-card')
    await within(card).findByTestId('price-bar')
    expect(card).toHaveAttribute('data-status', 'ok')
    expect(within(card).getAllByTestId('price-legend-item').map((item) => item.getAttribute('data-key'))).toEqual([
      'doctor_pay', 'drugs', 'anesthesia', 'supplies', 'acquiring', 'fixed', 'taxes', 'net',
    ])
    expect(within(card).getAllByTestId('price-legend-share')).toHaveLength(8)
    expect(within(card).getByTestId('price-bar')).toHaveAttribute('aria-label', expect.stringContaining('Из чего состоит цена'))
    expect(numbersWithoutTip(card)).toEqual([])
  })

  it('shows the banner and no bar for a service without a recipe', async () => {
    renderPrice(`/price?service=${NO_RECIPE}`)
    const missing = await screen.findByTestId('price-card-missing')
    expect(missing).toHaveAttribute('data-missing', 'recipe')
    expect(missing).toHaveTextContent('Нет техкарты: без неё прибыль была бы завышена, поэтому мы её не считаем.')
    expect(screen.getByText('Полоса появится, когда будет техкарта')).toBeInTheDocument()
    expect(screen.queryByTestId('price-bar')).not.toBeInTheDocument()
    expect(screen.getByTestId('price-card-net')).toHaveTextContent('—')
    expect(screen.getByTestId('price-minutes-note')).toHaveTextContent('длительность средняя по клинике, 30 мин')
  })

  it('shows a loss in words and with the minus sign', async () => {
    renderPrice(`/price?service=${WARD}`)
    const net = await screen.findByTestId('price-card-net')
    expect(net.textContent).toContain('−')
    expect(screen.getByTestId('price-card')).toHaveTextContent('в минус')
  })

  it('saves a recipe and the card gets its parts', async () => {
    const user = userEvent.setup()
    renderPrice(`/price?service=${NO_RECIPE}`)
    await user.click(await screen.findByRole('button', { name: 'Заполнить техкарту' }))
    const dialog = await screen.findByTestId('price-recipe-dialog')
    const minutes = await within(dialog).findByTestId('price-recipe-field-minutes')
    await user.type(minutes, '15')
    await user.click(within(dialog).getByTestId('price-recipe-save'))
    expect(await screen.findByText('Техкарта сохранена')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('price-card')).toHaveAttribute('data-status', 'ok'))
    expect(screen.getByTestId('price-bar')).toBeInTheDocument()
  })

  it('names the mistake of the recipe form without a request', async () => {
    const user = userEvent.setup()
    renderPrice(`/price?service=${NO_RECIPE}`)
    await user.click(await screen.findByTestId('price-card-edit'))
    const dialog = await screen.findByTestId('price-recipe-dialog')
    await user.type(await within(dialog).findByTestId('price-recipe-field-minutes'), '2000')
    await user.click(within(dialog).getByTestId('price-recipe-save'))
    expect(await within(dialog).findByTestId('price-recipe-field-minutes-error')).toHaveTextContent('От 1 до 1440 минут')
  })
})

describe('PricePage: a manual service', () => {
  it('adds a service, opens its card and deletes it', async () => {
    const user = userEvent.setup()
    renderPrice()
    await loaded()
    await user.click(screen.getAllByTestId('price-add')[0] as HTMLElement)
    const dialog = await screen.findByTestId('price-service-dialog')
    await user.click(within(dialog).getByTestId('price-service-save'))
    expect(await within(dialog).findByTestId('price-service-field-name-error')).toHaveTextContent('Напишите название услуги')
    expect(within(dialog).getByTestId('price-service-field-price-error')).toHaveTextContent('Укажите цену')
    await user.type(within(dialog).getByTestId('price-service-field-name'), 'Груминг: стрижка')
    await user.type(within(dialog).getByTestId('price-service-field-price'), '1800')
    await user.click(within(dialog).getByTestId('price-service-save'))
    expect(await screen.findByText('Услуга добавлена')).toBeInTheDocument()
    const card = await screen.findByTestId('price-card')
    await waitFor(() => expect(card).toHaveAttribute('data-status', 'no_recipe'))
    expect(await within(card).findByTestId('price-source')).toHaveAttribute('data-source', 'manual')

    await user.click(within(card).getByTestId('price-service-edit'))
    await user.click(await screen.findByTestId('price-service-delete'))
    await user.click(await screen.findByTestId('price-service-delete-confirm'))
    expect(await screen.findByText('Услуга удалена')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByTestId('price-card')).not.toBeInTheDocument())
  })

  it('refuses a duplicate name', async () => {
    const user = userEvent.setup()
    renderPrice()
    await loaded()
    await user.click(screen.getAllByTestId('price-add')[0] as HTMLElement)
    const dialog = await screen.findByTestId('price-service-dialog')
    await user.type(within(dialog).getByTestId('price-service-field-name'), 'кастрация  КОТА')
    await user.type(within(dialog).getByTestId('price-service-field-price'), '100')
    await user.click(within(dialog).getByTestId('price-service-save'))
    expect(await within(dialog).findByTestId('price-service-field-name-error')).toHaveTextContent('Такая услуга уже есть')
  })
})
