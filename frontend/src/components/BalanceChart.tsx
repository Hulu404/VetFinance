import { useId, useRef, useState, type KeyboardEvent } from 'react'
import type { BalanceTrendInfo, Figure, TrendPoint } from '../api/types'
import { formatDayMonth } from '../lib/dates'
import { formatMoney, pluralRu } from '../lib/format'
import { FigureTip } from './FigureTip'
import './BalanceChart.css'

const CHART_WIDTH = 760
const CHART_HEIGHT = 104
/** Margins of the drawing, percent of the height (design/components.md, section 16). */
const PAD_TOP = 12
const PAD_SPAN = 76
const MIN_POINTS = 2

export const CHART_EMPTY_TEXT = 'Динамика появится, когда накопится несколько дней данных.'

interface BalanceChartProps {
  points: TrendPoint[] | undefined
  /** Note and sources of every point's tip (a point has no breakdown of its own). */
  info?: BalanceTrendInfo
}

/** Drawing scale only: positions in percent. This is not money arithmetic. */
function scaleY(value: number, min: number, max: number): number {
  return max === min ? 50 : PAD_TOP + ((max - value) / (max - min)) * PAD_SPAN
}

function scaleX(index: number, count: number): number {
  return (index / (count - 1)) * 100
}

function pointFigure(point: TrendPoint, info: BalanceTrendInfo | undefined): Figure {
  return { value: point.value, unit: 'rub', breakdown: [], source: info?.source ?? [], note: info?.note ?? '' }
}

export function ChartEmpty() {
  return (
    <div className="chart-empty" data-testid="balance-chart-empty">
      {CHART_EMPTY_TEXT}
    </div>
  )
}

function targetIndex(key: string, index: number, count: number): number | null {
  switch (key) {
    case 'ArrowRight':
      return index + 1
    case 'ArrowLeft':
      return index - 1
    case 'Home':
      return 0
    case 'End':
      return count - 1
    default:
      return null
  }
}

/**
 * Balance at the end of each day. One Tab stop; arrows, Home and End move between days; every day opens a tip.
 * The same series is in a hidden table for screen readers.
 */
export function BalanceChart({ points, info }: BalanceChartProps) {
  const gradientId = useId()
  const areaRef = useRef<HTMLDivElement | null>(null)
  const [current, setCurrent] = useState<number | null>(null)

  if (!points || points.length < MIN_POINTS) return <ChartEmpty />

  const count = points.length
  const first = points[0]
  const last = points[count - 1]
  if (!first || !last) return <ChartEmpty />
  const activeIndex = current !== null && current < count ? current : count - 1
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const line = points
    .map((point, index) => {
      const x = (scaleX(index, count) / 100) * CHART_WIDTH
      const y = (scaleY(point.value, min, max) / 100) * CHART_HEIGHT
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' L')
  const zeroY = (scaleY(0, min, max) / 100) * CHART_HEIGHT
  const crossesZero = min < 0 && max > 0
  const days = pluralRu(count, 'день', 'дня', 'дней')
  const label = `График остатка за ${count} ${days}: с ${formatMoney(first.value)} до ${formatMoney(last.value)}`

  const focusPoint = (index: number) => {
    const strips = areaRef.current?.querySelectorAll<HTMLButtonElement>('.chart__strip')
    strips?.[Math.min(Math.max(index, 0), count - 1)]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const target = targetIndex(event.key, index, count)
    if (target === null) return
    event.preventDefault()
    focusPoint(target)
  }

  return (
    <div className="chart" data-testid="balance-trend" role="group" aria-label={label}>
      <div className="chart__area" ref={areaRef} data-testid="balance-chart">
        <svg className="chart__svg" viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" className="chart__stop chart__stop--top" />
              <stop offset="1" className="chart__stop chart__stop--bottom" />
            </linearGradient>
          </defs>
          {crossesZero && <line className="chart__zero" x1="0" x2={CHART_WIDTH} y1={zeroY} y2={zeroY} />}
          <path d={`M${line} L${CHART_WIDTH},${CHART_HEIGHT} L0,${CHART_HEIGHT} Z`} fill={`url(#${gradientId})`} />
          <path d={`M${line}`} className="chart__line" />
        </svg>
        {points.map((point, index) => {
          const left = index === 0 ? 0 : (scaleX(index, count) + scaleX(index - 1, count)) / 2
          const right = index === count - 1 ? 100 : (scaleX(index, count) + scaleX(index + 1, count)) / 2
          const dotLeft = ((scaleX(index, count) - left) / (right - left)) * 100
          const date = formatDayMonth(point.date)
          return (
            <span
              key={point.date}
              className="chart__point"
              style={{ left: `${left}%`, width: `${right - left}%` }}
              data-testid="balance-chart-point"
              data-figure="balance_trend"
              data-date={point.date}
            >
              <FigureTip figure={pointFigure(point, info)} title={`Остаток · ${date}`} emoji="💰">
                {(triggerProps) => (
                  <button
                    {...triggerProps}
                    type="button"
                    className={index === count - 1 ? 'chart__strip chart__strip--last' : 'chart__strip'}
                    tabIndex={index === activeIndex ? 0 : -1}
                    aria-label={`${date}, ${formatMoney(point.value)}`}
                    onFocus={(event) => {
                      triggerProps.onFocus(event)
                      setCurrent(index)
                    }}
                    onKeyDown={(event) => {
                      triggerProps.onKeyDown(event)
                      onKeyDown(event, index)
                    }}
                  >
                    <span
                      className="chart__dot"
                      aria-hidden="true"
                      style={{ left: `${dotLeft}%`, top: `${scaleY(point.value, min, max)}%` }}
                    />
                  </button>
                )}
              </FigureTip>
            </span>
          )
        })}
      </div>
      <table className="sr-only" data-no-tip>
        <caption>Остаток на конец дня</caption>
        <thead>
          <tr>
            <th scope="col">Дата</th>
            <th scope="col">Остаток</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.date}>
              <td>{formatDayMonth(point.date)}</td>
              <td>{formatMoney(point.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
