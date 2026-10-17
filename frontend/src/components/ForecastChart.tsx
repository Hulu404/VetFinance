import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import type { CalendarDay, CalendarReport, Figure } from '../api/types'
import { formatDayMonth } from '../lib/dates'
import { formatMoney, pluralDays } from '../lib/format'
import { dayTitle, isRedDay, RED_DAY_WORDS } from '../lib/planning'
import { FigureButton } from './FigureButton'
import { FigureTip } from './FigureTip'
import './ForecastChart.css'

/** Size before the first measurement (and in tests without ResizeObserver). */
const FALLBACK_WIDTH = 760
const FALLBACK_HEIGHT = 210
const PAD_X = 14
const PAD_Y = 18
const MIN_POINTS = 2
export const SAFE_SETTINGS_LINK = '/settings/main#safe-balance'

interface ForecastChartProps {
  days: CalendarDay[]
  safe: Figure
  safeSet: boolean
  /** Some day is below the safe balance: only then the legend explains the red point. */
  anyRed: boolean
  lowest: CalendarReport['summary']['lowest']
  selectedDate: string | null
  onSelect: (date: string) => void
}

interface Size {
  width: number
  height: number
}

/** Drawing scale only (pixels from the values the API gave). This is not money arithmetic. */
function scale(value: number, min: number, max: number, top: number, bottom: number): number {
  return max === min ? (top + bottom) / 2 : top + ((max - value) / (max - min)) * (bottom - top)
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

function useMeasuredSize() {
  const ref = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState<Size>({ width: FALLBACK_WIDTH, height: FALLBACK_HEIGHT })
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      const box = element.getBoundingClientRect()
      if (box.width > 0 && box.height > 0) setSize({ width: Math.round(box.width), height: Math.round(box.height) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return { ref, size }
}

/** Text for screen readers, made of the numbers of the answer. */
function chartLabel(days: CalendarDay[], lowest: ForecastChartProps['lowest']): string {
  const first = days[0]
  const last = days[days.length - 1]
  if (!first || !last) return ''
  const tail = isRedDay(lowest.status) ? `, ${RED_DAY_WORDS}` : ''
  return `Остаток на ${days.length} ${pluralDays(days.length)}: утром ${formatDayMonth(first.date)} ${formatMoney(first.opening.value)}, вечером ${formatDayMonth(last.date)} ${formatMoney(last.closing.value)}, самый низкий ${formatMoney(lowest.balance.value)} ${formatDayMonth(lowest.date)}${tail}`
}

/**
 * The balance at the end of each day for the 22 days of the window, the dashed safe balance and red points for the days
 * below it (design/components.md, section 23). Drawn in pixels of the measured width. One Tab stop; arrows, Home and End
 * move between points; Enter or a click selects the day.
 */
export function ForecastChart({ days, safe, safeSet, anyRed, lowest, selectedDate, onSelect }: ForecastChartProps) {
  const gradientId = useId()
  const { ref, size } = useMeasuredSize()
  const areaRef = useRef<HTMLDivElement | null>(null)
  const [current, setCurrent] = useState<number | null>(null)

  const count = days.length
  const first = days[0]
  const last = days[count - 1]
  if (count < MIN_POINTS || !first || !last) return null

  const selectedIndex = Math.max(0, days.findIndex((day) => day.date === selectedDate))
  const activeIndex = current !== null && current < count ? current : selectedIndex
  const values = days.map((day) => day.closing.value)
  const safeValue = safeSet ? safe.value : 0
  const min = Math.min(0, safeValue, ...values)
  const max = Math.max(safeValue, ...values)
  const { width, height } = size
  const xAt = (index: number) => PAD_X + (index / (count - 1)) * (width - PAD_X * 2)
  const yAt = (value: number) => scale(value, min, max, PAD_Y, height - PAD_Y)
  const line = values.map((value, index) => `${index === 0 ? 'M' : 'L'}${xAt(index).toFixed(1)},${yAt(value).toFixed(1)}`).join(' ')
  const area = `${line} L${xAt(count - 1).toFixed(1)},${height} L${xAt(0).toFixed(1)},${height} Z`
  const zeroY = yAt(0)

  const focusPoint = (index: number) => {
    const buttons = areaRef.current?.querySelectorAll<HTMLButtonElement>('button[data-point]')
    buttons?.[Math.min(Math.max(index, 0), count - 1)]?.focus()
  }

  return (
    <div className="fchart" data-testid="calendar-chart">
      <div className="fchart__area" ref={ref}>
        <svg
          className="fchart__svg"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={chartLabel(days, lowest)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" className="fchart__stop fchart__stop--top" />
              <stop offset="1" className="fchart__stop fchart__stop--bottom" />
            </linearGradient>
          </defs>
          {min < 0 && <line className="fchart__zero" x1={0} x2={width} y1={zeroY} y2={zeroY} />}
          <path d={area} fill={`url(#${gradientId})`} />
          <line className="fchart__safe-line" x1={0} x2={width} y1={yAt(safeValue)} y2={yAt(safeValue)} />
          <path d={line} className="fchart__line" />
        </svg>
        <div
          className="fchart__safe"
          data-testid="calendar-safe-line"
          style={{ top: yAt(safeValue) }}
          aria-hidden="true"
        />
        <div ref={areaRef} role="group" aria-label="Остаток на вечер по дням" className="fchart__points">
          {days.map((day, index) => {
            const red = isRedDay(day.status)
            const date = formatDayMonth(day.date)
            const label = `${dayTitle(day)}, остаток ${formatMoney(day.closing.value)}${red ? `, ${RED_DAY_WORDS}` : ''}`
            return (
              <FigureTip key={day.date} figure={day.closing} title={`Остаток на вечер · ${date}`} emoji="💰">
                {(trigger) => (
                  <button
                    {...trigger}
                    type="button"
                    className={`fchart__point${red ? ' fchart__point--bad' : ''}${index === 0 ? ' fchart__point--first' : ''}${day.date === selectedDate ? ' fchart__point--on' : ''}`}
                    style={{ left: xAt(index), top: yAt(day.closing.value) }}
                    tabIndex={index === activeIndex ? 0 : -1}
                    aria-label={label}
                    aria-pressed={day.date === selectedDate}
                    data-point=""
                    data-testid="calendar-chart-point"
                    data-figure={`days.${index}.closing`}
                    data-date={day.date}
                    data-status={day.status}
                    onFocus={(event) => {
                      trigger.onFocus(event)
                      setCurrent(index)
                    }}
                    onClick={(event) => {
                      if (event.detail > 0) trigger.onClick(event)
                      onSelect(day.date)
                    }}
                    onKeyDown={(event: KeyboardEvent) => {
                      trigger.onKeyDown(event)
                      const target = targetIndex(event.key, index, count)
                      if (target === null) return
                      event.preventDefault()
                      focusPoint(target)
                    }}
                  >
                    <span className="fchart__dot" aria-hidden="true" />
                  </button>
                )}
              </FigureTip>
            )
          })}
        </div>
      </div>
      <table className="sr-only" data-no-tip>
        <caption>Остаток на вечер по дням</caption>
        <thead>
          <tr>
            <th scope="col">Дата</th>
            <th scope="col">Остаток на вечер</th>
            <th scope="col">Статус</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <td>{formatDayMonth(day.date)}</td>
              <td>{formatMoney(day.closing.value)}</td>
              <td>{isRedDay(day.status) ? RED_DAY_WORDS : 'в порядке'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="fchart__captions">
        <span>{formatDayMonth(first.date)}, сегодня</span>
        <span className="fchart__legend" data-testid="calendar-chart-legend">
          {safeSet ? (
            <>
              пунктир: безопасный запас{' '}
              <FigureButton figure={safe} title="Безопасный запас" figureKey="safe_balance" />
              {anyRed && `; красная точка: ${RED_DAY_WORDS}`}
            </>
          ) : (
            <>
              Безопасный запас не задан · <Link to={SAFE_SETTINGS_LINK}>задать в Настройках</Link>
            </>
          )}
        </span>
        <span>{formatDayMonth(last.date)}</span>
      </div>
    </div>
  )
}
