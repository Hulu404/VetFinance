import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Figure } from '../api/types'
import { FigureTip } from './FigureTip'

// toHaveTextContent normalizes whitespace: non-breaking spaces compare as plain ones
const SP = ' '

const figure: Figure = {
  value: 41280000,
  unit: 'rub',
  breakdown: [
    { label: 'Расчётный счёт', value: 34130000, unit: 'rub' },
    { label: 'Касса', value: 7150000, unit: 'rub' },
  ],
  source: ['bank', 'manual'],
  note: 'Примечание от backend.',
}

function Harness({ value = figure }: { value?: Figure }) {
  return (
    <div>
      <FigureTip figure={value} title="Остаток на счетах" emoji="💰">
        {(props) => (
          <button type="button" {...props}>
            Сумма
          </button>
        )}
      </FigureTip>
      <button type="button">Другая кнопка</button>
    </div>
  )
}

describe('FigureTip', () => {
  it('is closed by default and not in the document', () => {
    render(<Harness />)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens on keyboard focus and shows breakdown, note and sources as given', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.tab()

    const tip = await screen.findByRole('tooltip')
    expect(tip).toHaveAttribute('data-testid', 'figure-tip')
    expect(tip).toHaveTextContent('Расчётный счёт')
    expect(tip).toHaveTextContent(`341${SP}300${SP}₽`)
    expect(tip).toHaveTextContent('Касса')
    expect(tip).toHaveTextContent('Примечание от backend.')
    expect(tip).toHaveTextContent('Банк')
    expect(tip).toHaveTextContent('Внесено вручную')
    expect(screen.getByRole('button', { name: 'Сумма' })).toHaveAttribute('aria-describedby', tip.id)
  })

  it('closes on Escape and keeps focus on the trigger', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.tab()
    await screen.findByRole('tooltip')

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сумма' })).toHaveFocus()
  })

  it('closes when focus leaves the trigger', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.tab()
    await screen.findByRole('tooltip')

    await user.tab()

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens on hover after a short delay and closes after leaving', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.hover(screen.getByRole('button', { name: 'Сумма' }))
    expect(await screen.findByRole('tooltip')).toBeInTheDocument()

    await user.unhover(screen.getByRole('button', { name: 'Сумма' }))
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens and closes by Enter', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.tab()
    await screen.findByRole('tooltip')

    await user.keyboard('{Enter}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    await user.keyboard('{Enter}')
    expect(await screen.findByRole('tooltip')).toBeInTheDocument()
  })

  it('does not draw blocks that have no data', async () => {
    const user = userEvent.setup()
    render(<Harness value={{ value: 100, unit: 'rub', breakdown: [], source: [], note: '' }} />)

    await user.tab()

    const tip = await screen.findByRole('tooltip')
    expect(tip).not.toHaveTextContent('Источник')
    expect(tip.querySelector('ul')).toBeNull()
  })

  it('marks negative rows with a minus sign', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        value={{
          value: -100,
          unit: 'rub',
          breakdown: [{ label: 'Счёт', value: -100, unit: 'rub' }],
          source: ['bank'],
          note: 'x',
        }}
      />,
    )
    await user.tab()
    const tip = await screen.findByRole('tooltip')
    expect(tip).toHaveTextContent('−')
  })

  it('signs a delta figure and its rows, and keeps reference rows apart from the breakdown', async () => {
    const user = userEvent.setup()
    const delta: Figure = {
      value: 1540000,
      unit: 'rub',
      delta: true,
      breakdown: [
        { label: 'Неделю назад (2 сентября)', value: 39740000, unit: 'rub' },
        { label: 'Сейчас', value: 41280000, unit: 'rub' },
        { label: 'Изменение', value: 1540000, unit: 'rub', delta: true },
      ],
      details: [{ label: 'Приёмов', value: 154, unit: 'count' }],
      source: ['bank'],
      note: 'Сравниваем остаток сегодня и 7 дней назад.',
    }
    render(<Harness value={delta} />)

    await user.tab()

    const tip = await screen.findByRole('tooltip')
    expect(tip).toHaveTextContent(`+15${SP}400${SP}₽`)
    expect(screen.getAllByTestId('figure-tip-row')).toHaveLength(3)
    expect(screen.getAllByTestId('figure-tip-detail')).toHaveLength(1)
    expect(screen.getByTestId('figure-tip-detail')).toHaveTextContent('Приёмов154')
    expect(screen.getByTestId('figure-tip-note')).toHaveTextContent('Сравниваем остаток')
    expect(screen.getByTestId('figure-tip-source')).toHaveTextContent('Банк')
  })
})
