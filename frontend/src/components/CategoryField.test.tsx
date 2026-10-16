import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { CATEGORIES } from '../mocks/txStore'
import { CategoryField } from './CategoryField'

it.each(['tax', 'obligation', 'capex', 'owner_draw'] as const)(
  'lets an outgoing transaction select a %s category', async (type) => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const category = CATEGORIES.find((item) => item.type === type)!
    render(<CategoryField label="Статья" categories={CATEGORIES} kind="out" value={null}
      loading={false} loadError={false} onRetry={vi.fn()} onChange={onChange} defaultOpen />)
    await user.type(screen.getByRole('combobox'), category.name)
    await user.click(screen.getByRole('option', { name: category.name }))
    expect(onChange).toHaveBeenCalledWith(category.id)
  },
)

it('keeps all expense types out of the incoming category list', () => {
  render(<CategoryField label="Статья" categories={CATEGORIES} kind="in" value={null}
    loading={false} loadError={false} onRetry={vi.fn()} onChange={vi.fn()} defaultOpen />)
  expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['Выручка', 'Выручка (эквайринг)'])
})
