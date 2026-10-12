import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { setMockScenario } from '../../mocks/scenario'
import { renderWithQuery } from '../../test/render'
import { BankSection } from './BankSection'
import { VetmanagerSection } from './VetmanagerSection'

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  const { fakeUpload } = await import('../../test/uploadShim')
  return { ...actual, apiUpload: fakeUpload }
})

function openVetmanager() {
  return renderWithQuery(<VetmanagerSection />, { toasts: true })
}

describe('Vetmanager section', () => {
  it('shows the state in words, the masked key with the last four characters, and the fixed schedule', async () => {
    openVetmanager()

    const card = await screen.findByTestId('vm-card')
    expect(within(card).getByText('обновлено сегодня в 04:12')).toBeInTheDocument()
    expect(within(card).getByDisplayValue('••••••••••••4a7f')).toBeDisabled()
    expect(within(card).getByLabelText('Ключ скрыт, последние четыре знака 4 a 7 f')).toBeInTheDocument()
    expect(within(card).getByText('Каждую ночь в 04:00')).toBeInTheDocument()
    expect(within(card).getByLabelText('Адрес системы')).toHaveValue('aibolit.vetmanager.ru')
    expect(within(card).queryByDisplayValue('4a7f')).not.toBeInTheDocument()
    expect(screen.queryByText('Работа без Ветменеджера')).not.toBeInTheDocument()
  })

  it('lists the last five runs with a tip on the counter and the reason of a failed one', async () => {
    const user = userEvent.setup()
    openVetmanager()

    const runs = await screen.findAllByTestId('sync-run')
    expect(runs).toHaveLength(5)
    expect(runs[0]).toHaveTextContent('успешно')
    expect(runs[1]).toHaveTextContent('частично')
    expect(runs[2]).toHaveTextContent('ошибка')
    expect(runs[2]).toHaveTextContent('Ветменеджер не отвечает')
    expect(within(runs[2] as HTMLElement).getByText('—')).toBeInTheDocument()

    await user.hover(within(runs[0] as HTMLElement).getByRole('button', { name: /показать из чего состоит/ }))
    const tip = await screen.findByTestId('figure-tip')
    expect(tip).toHaveTextContent('Новых операций')
    expect(tip).toHaveTextContent('Пропущено как дубли')
  })

  it('replaces the key only on request and never shows the old one', async () => {
    const user = userEvent.setup()
    openVetmanager()
    const card = await screen.findByTestId('vm-card')

    await user.click(within(card).getByRole('button', { name: 'Заменить ключ' }))
    const key = within(card).getByLabelText('Ключ доступа')
    expect(key).toHaveValue('')
    expect(key).toHaveAttribute('type', 'password')
    expect(key).toHaveFocus()
    await user.click(within(card).getByRole('button', { name: 'Не менять' }))
    expect(within(card).getByDisplayValue('••••••••••••4a7f')).toBeDisabled()
  })

  it('shows the server error under the key field and keeps the typed address', async () => {
    const user = userEvent.setup()
    openVetmanager()
    const card = await screen.findByTestId('vm-card')

    await user.click(within(card).getByRole('button', { name: 'Заменить ключ' }))
    await user.type(within(card).getByLabelText('Ключ доступа'), 'wrong-key-0000')
    await user.click(within(card).getByTestId('vm-save'))

    expect(await within(card).findByText('Ветменеджер не принял ключ. Проверьте ключ и адрес')).toBeInTheDocument()
    expect(within(card).getByLabelText('Адрес системы')).toHaveValue('aibolit.vetmanager.ru')
  })

  it('saves a new key and shows only its last four characters afterwards', async () => {
    const user = userEvent.setup()
    openVetmanager()
    const card = await screen.findByTestId('vm-card')

    await user.click(within(card).getByRole('button', { name: 'Заменить ключ' }))
    await user.type(within(card).getByLabelText('Ключ доступа'), 'secret-key-9d2e')
    await user.click(within(card).getByTestId('vm-save'))

    expect(await screen.findByText('Подключение сохранено.')).toBeInTheDocument()
    await waitFor(() => expect(within(card).getByDisplayValue('••••••••••••9d2e')).toBeDisabled())
    expect(document.body.innerHTML).not.toContain('secret-key')
    expect(JSON.stringify(window.localStorage)).not.toContain('secret-key')
    expect(JSON.stringify(window.sessionStorage)).not.toContain('secret-key')
  })

  it('validates the address before sending', async () => {
    const user = userEvent.setup()
    openVetmanager()
    const card = await screen.findByTestId('vm-card')

    const address = within(card).getByLabelText('Адрес системы')
    await user.clear(address)
    await user.type(address, 'nodot')
    await user.click(within(card).getByTestId('vm-save'))
    expect(within(card).getByText('Адрес выглядит неверно. Пример: aibolit.vetmanager.ru')).toBeInTheDocument()

    await user.clear(address)
    await user.type(address, 'bad.example.ru')
    await user.click(within(card).getByTestId('vm-save'))
    expect(await within(card).findByText('Не удалось связаться с bad.example.ru. Проверьте адрес')).toBeInTheDocument()
  })

  it('runs a sync: busy button, then a toast with the number and a refreshed status', { timeout: 20_000 }, async () => {
    const user = userEvent.setup()
    openVetmanager()
    const card = await screen.findByTestId('vm-card')

    await user.click(within(card).getByTestId('vm-sync'))
    await waitFor(() => expect(within(card).getByTestId('vm-sync')).toHaveTextContent('Синхронизируем…'))
    expect(within(card).getByTestId('vm-sync')).toBeDisabled()

    expect(await screen.findByText('Ветменеджер обновлён: загружено 7 операций.', {}, { timeout: 10_000 })).toBeInTheDocument()
    await waitFor(() => expect(within(card).getByTestId('vm-sync')).toHaveTextContent('Синхронизировать'))
  })

  it('shows a failed run: reason in words, the date of the last success and "Заменить ключ" for a bad key', async () => {
    setMockScenario('syncerror')
    openVetmanager()

    const reason = await screen.findByTestId('vm-error')
    expect(reason).toHaveTextContent('Ветменеджер не принял ключ.')
    expect(reason).toHaveTextContent('Показаны данные на 8 сентября')
    expect(within(reason).getByRole('button', { name: 'Заменить ключ' })).toBeInTheDocument()
    expect(screen.getAllByText('ошибка синхронизации').length).toBeGreaterThan(0)
  })

  it('warns when the data are stale', async () => {
    setMockScenario('stale')
    openVetmanager()

    expect(await screen.findByTestId('vm-stale')).toHaveTextContent('Ветменеджер давно не обновлялся')
    expect(screen.getAllByText('данные устарели').length).toBeGreaterThan(0)
  })

  it('offers to connect when there is no connection and explains the work without it', async () => {
    const user = userEvent.setup()
    setMockScenario('notconnected')
    openVetmanager()

    const card = await screen.findByTestId('vm-card')
    expect(within(card).getByText('не подключено')).toBeInTheDocument()
    expect(within(card).queryByTestId('vm-sync')).not.toBeInTheDocument()
    expect(screen.getByText('Работа без Ветменеджера')).toBeInTheDocument()
    expect(screen.getByText('Запусков пока не было. Они появятся после подключения.')).toBeInTheDocument()

    await user.click(within(card).getByTestId('vm-save'))
    expect(within(card).getByText('Введите адрес вашего Ветменеджера')).toBeInTheDocument()
    await user.type(within(card).getByLabelText('Адрес системы'), 'aibolit.vetmanager.ru')
    await user.click(within(card).getByTestId('vm-save'))
    expect(within(card).getByText('Вставьте ключ из Ветменеджера', { selector: 'p' })).toBeInTheDocument()
  })

  it('has an error block with a retry when the connections do not load', async () => {
    const user = userEvent.setup()
    setMockScenario('txerror')
    openVetmanager()

    const error = await screen.findByTestId('vm-load-error')
    expect(error).toHaveTextContent('Не получилось загрузить подключения')
    setMockScenario('default')
    await user.click(within(error).getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByTestId('vm-card')).toBeInTheDocument()
  })
})

describe('Bank section', () => {
  it('shows the last statement date and a row per account', async () => {
    renderWithQuery(<BankSection />, { toasts: true })

    expect(await screen.findByText('последняя выписка по 9 сентября')).toBeInTheDocument()
    const rows = screen.getAllByTestId('bank-account')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('выписка по 9 сентября')
    expect(screen.getByText(/Подключение банка напрямую появится позже/)).toBeInTheDocument()
  })

  it('says that no statements were loaded yet', async () => {
    setMockScenario('notconnected')
    renderWithQuery(<BankSection />, { toasts: true })

    expect(await screen.findByText('выписок ещё не было', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getAllByText('выписок ещё не было').length).toBeGreaterThan(1)
  })

  it('opens the upload dialog with the account chosen in advance and refreshes the date after the upload', async () => {
    const user = userEvent.setup()
    renderWithQuery(<BankSection />, { toasts: true })
    const rows = await screen.findAllByTestId('bank-account')

    await user.click(within(rows[1] as HTMLElement).getByRole('button', { name: /Загрузить выписку для счёта/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Загрузка выписки' })
    await within(dialog).findByRole('option', { name: 'Резервный счёт' })
    expect(within(dialog).getByTestId('import-account')).toHaveValue('A-bank2')

    await user.upload(
      within(dialog).getByTestId('import-file'),
      new File(['1CClientBankExchange\n'], 'statement.txt', { type: 'text/plain' }),
    )
    await user.click(within(dialog).getByTestId('import-submit'))
    expect(await screen.findByTestId('import-result')).toBeInTheDocument()
  })
})
