import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { setMockScenario, type MockScenario } from '../../mocks/scenario'
import { renderWithQuery } from '../../test/render'
import { TransactionsPage } from './TransactionsPage'

function open(path = '/transactions') {
  return renderWithQuery(<TransactionsPage />, { toasts: true, path })
}

async function rows() {
  return screen.findAllByTestId('tx-row')
}

describe('TransactionsPage: the list "Все"', () => {
  it('shows the first page of the month with a "Показать ещё" button and the month summary with tips', async () => {
    const user = userEvent.setup()
    open()

    expect(screen.getByRole('heading', { level: 1, name: 'Транзакции' })).toBeInTheDocument()
    expect(screen.getByText('Загружаем операции')).toBeInTheDocument()
    expect(await rows()).toHaveLength(50)
    expect(screen.getByRole('heading', { name: 'Сентябрь 2026' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Показать ещё' }))
    await waitFor(() => expect(screen.getAllByTestId('tx-row')).toHaveLength(55))
    expect(screen.queryByRole('button', { name: 'Показать ещё' })).not.toBeInTheDocument()

    expect(await screen.findByTestId('summary-income')).toHaveTextContent('₽')
    expect(screen.getByTestId('summary-expense')).toHaveTextContent('₽')
    expect(screen.getByTestId('summary-balance')).toHaveTextContent('Сальдо')
  })

  it('gives each amount a tip, marks duplicates and transfers with words', async () => {
    const user = userEvent.setup()
    open('/transactions?month=2026-09')
    await rows()

    const transfer = screen.getAllByTestId('tx-row').find((row) => within(row).queryByText('перевод между счетами'))
    expect(transfer).toBeDefined()
    const amount = within(transfer as HTMLElement).getByTestId('tx-amount')
    await user.hover(within(amount).getByRole('button'))
    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Операция')
    expect(tip).toHaveTextContent('Источник:')
  })

  it('moves to another month and shows the empty state of that month', async () => {
    const user = userEvent.setup()
    open()
    await rows()

    await user.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))
    await user.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))

    expect(await screen.findByText('За июль 2026 операций нет')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Следующий месяц' })).toBeEnabled()
  })

  it('does not allow a month after the current one', async () => {
    open()
    await rows()
    expect(screen.getByRole('button', { name: 'Следующий месяц' })).toBeDisabled()
  })

  it('shows the empty state when there are no operations at all', async () => {
    setMockScenario('txempty')
    open()

    expect(await screen.findByText('Операций пока нет')).toBeInTheDocument()
    expect(screen.getByTestId('tx-list')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Подключить Ветменеджер' })).toHaveAttribute('href', '/settings/connections/vetmanager')
  })

  it('shows an error block with a retry when the list does not load', async () => {
    const user = userEvent.setup()
    setMockScenario('txerror')
    open()

    const alert = await screen.findByTestId('tx-error')
    expect(alert).toHaveTextContent('Не получилось загрузить операции')
    expect(alert).toHaveTextContent('не загрузилось')

    setMockScenario('default')
    await user.click(within(alert).getByRole('button', { name: 'Повторить' }))
    expect(await rows()).not.toHaveLength(0)
  })
})

describe('TransactionsPage: banners', () => {
  async function banner(scenario: MockScenario, testId: string) {
    setMockScenario(scenario)
    open()
    return screen.findByTestId(testId)
  }

  it('says that the data may be stale and links to the connections', async () => {
    const strip = await banner('stale', 'banner-stale')
    expect(strip).toHaveTextContent('могли устареть')
    expect(within(strip).getByRole('link', { name: 'Открыть подключения' })).toHaveAttribute(
      'href',
      '/settings/connections/vetmanager',
    )
    expect(await screen.findByText('данные устарели')).toBeInTheDocument()
  })

  it('shows the sync error with the reason from the code and hides the stale strip', async () => {
    const strip = await banner('syncerror', 'banner-sync-error')
    expect(strip).toHaveTextContent('Ветменеджер не удалось обновить: ключ не подошёл.')
    expect(strip).toHaveTextContent('Показаны данные на 8 сентября')
    expect(screen.queryByTestId('banner-stale')).not.toBeInTheDocument()
  })

  it('has no strip when everything is fine', async () => {
    open()
    await rows()
    expect(screen.queryByTestId('banner-stale')).not.toBeInTheDocument()
    expect(screen.queryByTestId('banner-sync-error')).not.toBeInTheDocument()
  })
})

describe('TransactionsPage: "На проверку" and the category dialog', () => {
  it('lists operations without a category with a count in the tab and a hint about all months', async () => {
    open('/transactions?tab=check')

    const list = await screen.findAllByTestId('tx-row')
    expect(list).toHaveLength(6)
    expect(screen.getByText('Показаны операции за все месяцы.')).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: /На проверку/ })).toHaveTextContent('6')
    for (const row of list) expect(within(row).getByTestId('tx-category')).toBeInTheDocument()
  })

  it('confirms the suggestion in one click and creates the rule for "similar"', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=check')

    const row = (await rows()).find((item) => within(item).queryByTestId('tx-confirm'))
    expect(row).toBeDefined()
    expect(row).toHaveTextContent('Предлагаем «Препараты»: Так же разнесено 2 операции по «Вет-Снаб»')
    await user.click(within(row as HTMLElement).getByTestId('tx-confirm'))

    expect(await screen.findByText(/Статья «Препараты» сохранена\. Правило создано/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('tx-row')).toHaveLength(5))
  })

  it('creates a rule from the dialog: the checkbox is on, the preview gives the number, the toast tells the result', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=check')

    const row = (await rows()).find((item) => within(item).queryByText(/аренда за сентябрь/))
    await user.click(within(row as HTMLElement).getByTestId('tx-category'))

    const dialog = await screen.findByRole('dialog', { name: 'Статья для операции' })
    expect(within(dialog).getByTestId('create-rule')).toBeChecked()
    expect(within(dialog).getByText('Выберите статью, и мы покажем, к скольким операциям применится правило.')).toBeInTheDocument()

    await user.click(within(screen.getByTestId('category-picker')).getByRole('option', { name: 'Аренда' }))
    expect(
      await within(dialog).findByText(/Правило: если контрагент «ИП Волков», статья «Аренда»\. Применится к 1 уже загруженной операции/),
    ).toBeInTheDocument()

    await user.click(within(dialog).getByTestId('category-save'))
    expect(await screen.findByText(/Статья «Аренда» сохранена\. Правило создано и применилось ещё к 1 операции\./)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('tx-row')).toHaveLength(4))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Посмотреть правило' }))
    const ruleRows = await screen.findAllByTestId('rule-row')
    expect(ruleRows[0]).toHaveTextContent('ИП Волков')
  })

  it('without the checkbox only this operation changes and the text says so', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=check')

    const row = (await rows()).find((item) => within(item).queryByText(/аренда за сентябрь/))
    await user.click(within(row as HTMLElement).getByTestId('tx-category'))
    const dialog = await screen.findByRole('dialog', { name: 'Статья для операции' })
    await user.click(within(screen.getByTestId('category-picker')).getByRole('option', { name: 'Аренда' }))
    await within(dialog).findByText(/Применится к 1/)
    await user.click(within(dialog).getByTestId('create-rule'))
    expect(within(dialog).getByText('Изменится только эта операция.')).toBeInTheDocument()
    await user.click(within(dialog).getByTestId('category-save'))

    expect(await screen.findByText('Статья «Аренда» сохранена.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('tx-row')).toHaveLength(5))
  })

  it('asks before discarding a changed form and requires a category', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=check')
    const row = (await rows())[0] as HTMLElement
    await user.click(within(row).getByTestId('tx-category'))
    const dialog = await screen.findByRole('dialog', { name: 'Статья для операции' })

    await user.click(within(dialog).getByTestId('category-save'))
    expect(within(dialog).getByText('Выберите статью')).toBeInTheDocument()

    await user.click(within(dialog).getByTestId('create-rule'))
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }))
    expect(await screen.findByText('Закрыть без сохранения?')).toBeInTheDocument()
  })
})

describe('TransactionsPage: duplicates', () => {
  it('shows pairs with two rows and a button on each, no red "Удалить"', async () => {
    open('/transactions?tab=duplicates')

    const pairs = await screen.findAllByTestId('dup-pair')
    expect(pairs).toHaveLength(2)
    const first = pairs[0] as HTMLElement
    expect(within(first).getAllByTestId('tx-row')).toHaveLength(2)
    expect(within(first).getAllByTestId('keep-this')).toHaveLength(2)
    expect(within(first).getByText('Уже была в учёте')).toBeInTheDocument()
    expect(within(first).getByText('Пришла повторно')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Удалить/ })).not.toBeInTheDocument()
    expect(first).toHaveTextContent('Похоже на дубль · ')
  })

  it('resolves a pair in one action and updates the counts', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=duplicates')
    const pairs = await screen.findAllByTestId('dup-pair')

    await user.click(within(pairs[0] as HTMLElement).getAllByTestId('keep-this')[1] as HTMLElement)

    expect(await screen.findByText(/^Оставили операцию от \d+ \S+ \(\S+\)\. Вторая не учитывается\.$/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('dup-pair')).toHaveLength(1))
  })

  it('"Это не дубль" keeps both', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=duplicates')
    const pairs = await screen.findAllByTestId('dup-pair')

    await user.click(within(pairs[0] as HTMLElement).getByRole('button', { name: 'Это не дубль, оставить обе' }))

    expect(await screen.findByText('Обе операции остались в учёте.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('dup-pair')).toHaveLength(1))
  })
})

describe('TransactionsPage: rules', () => {
  it('lists the rules with a tip on the counter and deletes one after a question', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=rules')

    const list = await screen.findAllByTestId('rule-row')
    expect(list).toHaveLength(2)
    await user.hover(within(list[0] as HTMLElement).getByRole('button', { name: /показать из чего состоит/ }))
    expect(await screen.findByTestId('figure-tip')).toHaveTextContent('В этом месяце')

    await user.click(within(list[0] as HTMLElement).getByRole('button', { name: /Удалить правило/ }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Уже разнесённые операции останутся в своих статьях.')
    await user.click(within(dialog).getByRole('button', { name: 'Удалить правило' }))

    expect(await screen.findByText('Правило удалено.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('rule-row')).toHaveLength(1))
  })
})
