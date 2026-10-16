import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Figure } from '../api/types'
import { StructureBar, type StructureSegment } from './StructureBar'

function pct(value: number): Figure {
  return { value, unit: 'pct', breakdown: [], source: ['calc'], note: 'n' }
}
function rub(value: number): Figure {
  return { value, unit: 'rub', breakdown: [{ label: 'Часть', value, unit: 'rub' }], source: ['bank'], note: 'n' }
}
function segment(key: string, label: string, share: number | null, color: number): StructureSegment {
  return { key, label, share: share === null ? null : pct(share), tip: rub(63200000), figureKey: `rows.${key}.share_pct`, color }
}

describe('StructureBar', () => {
  it('sizes the segments by the shares it was given and skips the tiny ones, which stay in the legend', () => {
    const { container } = render(
      <StructureBar
        caption="Куда уходит выручка"
        ariaLabel="Структура выручки"
        segments={[segment('a', 'Переменные расходы', 51, 1), segment('b', 'Налоги', 0.3, 2), segment('c', 'Прибыль', 12.3, 6)]}
      />,
    )

    const drawn = Array.from(container.querySelectorAll<HTMLElement>('.structure__seg'))
    expect(drawn.map((item) => item.style.flexGrow)).toEqual(['51', '12.3'])
    expect(screen.getAllByTestId('pnl-structure-item')).toHaveLength(3)
    expect(screen.getAllByTestId('pnl-structure-item')[1]).toHaveTextContent('Налоги0,3%')
  })

  it('gives the light colours a border, so the segment is visible without colour', () => {
    const { container } = render(<StructureBar caption="x" ariaLabel="x" segments={[segment('a', 'A', 10, 4), segment('b', 'B', 10, 1)]} />)

    const drawn = Array.from(container.querySelectorAll('.structure__seg'))
    expect(drawn[0]).toHaveClass('structure__seg--light')
    expect(drawn[1]).not.toHaveClass('structure__seg--light')
  })

  it('opens the figure of the row from a legend item and names it by label and share', () => {
    render(<StructureBar caption="x" ariaLabel="Структура" segments={[segment('a', 'Переменные расходы', 51, 1)]} />)

    const item = screen.getByTestId('pnl-structure-item')
    expect(item).toHaveAttribute('data-figure', 'rows.a.share_pct')
    expect(within(item).getByRole('button', { name: 'Переменные расходы, 51,0%, показать из чего состоит' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Структура' })).toBeInTheDocument()
  })

  it('draws no segment for a share the API did not give', () => {
    const { container } = render(<StructureBar caption="x" ariaLabel="x" segments={[segment('a', 'A', null, 1)]} />)

    expect(container.querySelectorAll('.structure__seg')).toHaveLength(0)
    expect(screen.getByTestId('pnl-structure-item')).toHaveTextContent('—')
  })
})
