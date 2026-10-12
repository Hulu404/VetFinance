import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { App } from './App'
import { setMockScenario } from './mocks/scenario'
import { renderWithAuth } from './test/render'

async function signIn(user: ReturnType<typeof userEvent.setup>, password = 'secret') {
  await user.type(await screen.findByLabelText('Почта'), 'owner@lapa.test')
  await user.type(screen.getByLabelText('Пароль'), password)
  await user.click(screen.getByRole('button', { name: 'Войти' }))
}

describe('App: login and shell', () => {
  it('sends anonymous users to the login screen', async () => {
    renderWithAuth(<App />, '/')

    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(screen.getByLabelText('Почта')).toBeInTheDocument()
    expect(screen.getByLabelText('Пароль')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument()
  })

  it('logs in with any credentials in mock mode and shows the balance', async () => {
    const user = userEvent.setup()
    renderWithAuth(<App />, '/')

    await signIn(user)

    const total = await screen.findByTestId('balance-total')
    expect(total).toHaveTextContent('₽')
    expect(screen.getByText('owner@lapa.test')).toBeInTheDocument()
    expect(await screen.findByText('Клиника «Лапа» (набор A)')).toBeInTheDocument()
  })

  it('validates empty fields and a malformed e-mail', async () => {
    const user = userEvent.setup()
    renderWithAuth(<App />, '/')

    await user.click(await screen.findByRole('button', { name: 'Войти' }))
    expect(screen.getByText('Введите почту')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Почта'), 'no-at-sign')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    expect(screen.getByText('Проверьте почту: похоже, в адресе опечатка')).toBeInTheDocument()
  })

  it('shows a generic message for wrong credentials and clears the password', async () => {
    const user = userEvent.setup()
    renderWithAuth(<App />, '/')

    await signIn(user, 'wrong')

    expect(await screen.findByRole('alert')).toHaveTextContent('Неверная почта или пароль')
    expect(screen.getByLabelText('Пароль')).toHaveValue('')
  })

  it('shows the menu with "Скоро" sections that cannot be opened and no Doctors section', async () => {
    const user = userEvent.setup()
    renderWithAuth(<App />, '/')
    await signIn(user)
    await screen.findByTestId('balance-total')

    const nav = screen.getByRole('navigation', { name: 'Основное меню' })
    expect(within(nav).getByRole('link', { name: 'Рабочий стол' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Транзакции' })).toHaveAttribute('href', '/transactions')
    expect(within(nav).getByRole('button', { name: /Прайс услуг/ })).toBeDisabled()
    expect(within(nav).getByRole('button', { name: /Отчёты/ })).toBeDisabled()
    expect(within(nav).queryByText('Врачи')).not.toBeInTheDocument()
  })

  it('signs out from the menu', async () => {
    const user = userEvent.setup()
    renderWithAuth(<App />, '/')
    await signIn(user)
    await screen.findByTestId('balance-total')

    await user.click(screen.getByRole('button', { name: 'Выйти' }))

    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
  })

  it('returns to the login screen with a notice when the API answers 401', async () => {
    const user = userEvent.setup()
    const { queryClient } = renderWithAuth(<App />, '/')
    await signIn(user)
    await screen.findByTestId('balance-total')

    setMockScenario('expired')
    await queryClient.invalidateQueries({ queryKey: ['dashboard'] })

    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(screen.getByText('Сессия закончилась. Войдите снова.')).toBeInTheDocument()
  })

  it('shows a stub for a section that is not ready when its address is typed', async () => {
    const user = userEvent.setup()
    renderWithAuth(<App />, '/price')
    await signIn(user)

    expect(await screen.findByRole('heading', { name: 'Прайс услуг' })).toBeInTheDocument()
    expect(screen.getByText('Этот раздел откроем позже. Сейчас доступен Рабочий стол.')).toBeInTheDocument()
  })

  it('shows the "not linked to a clinic" screen on forbidden', async () => {
    const user = userEvent.setup()
    setMockScenario('noclinic')
    renderWithAuth(<App />, '/')
    await signIn(user)

    expect(await screen.findByText('Ваша почта пока не привязана к клинике')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })
})
