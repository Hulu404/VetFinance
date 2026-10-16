import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { MonthSwitcher } from './MonthSwitcher'

function setup(props: Partial<ComponentProps<typeof MonthSwitcher>> = {}) {
  const onChange = vi.fn()
  render(
    <MonthSwitcher
      month="2026-08"
      firstMonth="2026-07"
      currentMonth="2026-10"
      periodStatus="closed"
      periodTo={null}
      loading={false}
      onChange={onChange}
      testIdPrefix="pnl"
      {...props}
    />,
  )
  return { onChange, user: userEvent.setup() }
}

describe('MonthSwitcher', () => {
  it('shows the month, the closed pill and moves one month back and forward', async () => {
    const { onChange, user } = setup()

    expect(screen.getByTestId('pnl-month')).toHaveTextContent('Август 2026')
    expect(screen.getByTestId('pnl-period-status')).toHaveTextContent('месяц закрыт')
    await user.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))
    await user.click(screen.getByRole('button', { name: 'Следующий месяц' }))

    expect(onChange).toHaveBeenNthCalledWith(1, '2026-07')
    expect(onChange).toHaveBeenNthCalledWith(2, '2026-09')
  })

  it('crosses the end of the year', async () => {
    const { onChange, user } = setup({ month: '2027-01', firstMonth: '2026-07', currentMonth: '2027-03' })

    await user.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))

    expect(onChange).toHaveBeenCalledWith('2026-12')
  })

  it('disables the previous month on the first month with data, with aria-disabled', async () => {
    const { onChange, user } = setup({ month: '2026-07' })

    const prev = screen.getByRole('button', { name: 'Предыдущий месяц' })
    expect(prev).toHaveAttribute('aria-disabled', 'true')
    await user.click(prev)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('disables the next month on the month of the reference date', async () => {
    const { onChange, user } = setup({ month: '2026-10' })

    const next = screen.getByRole('button', { name: 'Следующий месяц' })
    expect(next).toHaveAttribute('aria-disabled', 'true')
    await user.click(next)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('says in words that the month is going and up to which day the data reaches', () => {
    setup({ month: '2026-09', periodStatus: 'open', periodTo: '2026-09-09' })

    expect(screen.getByTestId('pnl-period-status')).toHaveTextContent('месяц идёт, данные по 9 сентября')
  })

  it('shows a placeholder instead of the month before the first answer and keeps the buttons inactive while loading', () => {
    setup({ month: null, periodStatus: undefined, loading: true })

    expect(screen.getByTestId('pnl-month').textContent).toBe('')
    expect(screen.getByRole('button', { name: 'Предыдущий месяц' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'Следующий месяц' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByTestId('pnl-period-status')).not.toBeInTheDocument()
  })
})
