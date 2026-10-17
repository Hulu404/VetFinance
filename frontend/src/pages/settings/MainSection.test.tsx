import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '../../test/render'
import { MainSection } from './MainSection'

describe('Safe balance card', () => {
  it('shows the toast on every save, although each saved value re-renders the card', async () => {
    const user = userEvent.setup()
    renderWithQuery(<MainSection />, { toasts: true })
    for (const rubles of ['250000', '150000']) {
      const input = await screen.findByTestId('settings-safe-balance-input')
      await user.clear(input)
      await user.type(input, rubles)
      await user.click(screen.getByTestId('settings-safe-balance-save'))

      expect(await screen.findByText('Запас сохранён')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Закрыть уведомление' }))
    }
  })
})
