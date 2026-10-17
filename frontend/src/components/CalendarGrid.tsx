import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { CalendarDay } from '../api/types'
import { formatMoney } from '../lib/format'
import {
  buildGrid,
  dayTitle,
  formatIncoming,
  formatOutgoing,
  isRedDay,
  moreLabel,
  monthStartLabel,
  RED_DAY_WORDS,
  WEEKDAY_HEADERS,
  weekdayIndex,
  type GridCell,
} from '../lib/planning'
import { FigureTip } from './FigureTip'
import './CalendarGrid.css'

/** Payments shown in a cell; the rest is a count "ещё N платежей" (the client does not add the sums up). */
const CELL_PAYMENTS = 2
const WEEK_LENGTH = 7

interface CalendarGridProps {
  days: CalendarDay[]
  selectedDate: string | null
  /** `byKeyboard`: Enter or Space moved the choice, so focus goes to the day breakdown. */
  onSelect: (date: string, byKeyboard: boolean) => void
  label: string
}

function cellLabel(day: CalendarDay, today: boolean): string {
  const red = isRedDay(day.status)
  return `${dayTitle(day)}${today ? ', сегодня' : ''}, остаток ${formatMoney(day.closing.value)}${red ? ', ниже безопасного запаса' : ''}`
}

/** Index of the day to move to for an arrow key, Home or End; null for other keys or when the window ends. */
function targetIndex(key: string, index: number, days: CalendarDay[]): number | null {
  const column = weekdayIndex(days[index]?.weekday ?? 'пн')
  const target =
    key === 'ArrowLeft'
      ? index - 1
      : key === 'ArrowRight'
        ? index + 1
        : key === 'ArrowUp'
          ? index - WEEK_LENGTH
          : key === 'ArrowDown'
            ? index + WEEK_LENGTH
            : key === 'Home'
              ? Math.max(0, index - column)
              : key === 'End'
                ? Math.min(days.length - 1, index + (WEEK_LENGTH - 1 - column))
                : null
  if (target === null) return null
  return target >= 0 && target < days.length ? target : index
}

interface DayCellProps {
  cell: Extract<GridCell, { kind: 'day' }>
  index: number
  selected: boolean
  tabStop: boolean
  onFocusDay: (date: string) => void
  onSelect: (date: string, byKeyboard: boolean) => void
  onKeyDown: (event: KeyboardEvent, index: number) => void
}

function DayCell({ cell, index, selected, tabStop, onFocusDay, onSelect, onKeyDown }: DayCellProps) {
  const { day, today } = cell
  const red = isRedDay(day.status)
  const shown = day.payments.slice(0, CELL_PAYMENTS)
  const hidden = day.payments.length - shown.length
  const weekend = day.weekday === 'сб' || day.weekday === 'вс'
  return (
    <div
      role="gridcell"
      className={`cal__cell${weekend ? ' cal__cell--weekend' : ''}${red ? ' cal__cell--bad' : ''}${selected ? ' cal__cell--on' : ''}`}
      data-testid="calendar-cell"
      data-date={day.date}
      data-status={day.status}
      data-today={today ? 'true' : undefined}
    >
      <FigureTip figure={day.closing} title={dayTitle(day)}>
        {(trigger) => (
          <button
            {...trigger}
            type="button"
            className="cal__btn"
            tabIndex={tabStop ? 0 : -1}
            aria-label={cellLabel(day, today)}
            aria-pressed={selected}
            data-cell-date={day.date}
            onFocus={() => onFocusDay(day.date)}
            onClick={(event) => onSelect(day.date, event.detail === 0)}
            onKeyDown={(event) => {
              trigger.onKeyDown(event)
              onKeyDown(event, index)
            }}
          >
            <span className="cal__top" aria-hidden="true">
              <span className={today ? 'cal__num cal__num--today' : 'cal__num'}>{cell.monthStart ? monthStartLabel(day.date) : cell.dayNumber}</span>
              {today && <span className="cal__today">сегодня</span>}
            </span>
            <span className="cal__ev cal__ev--in" aria-hidden="true" data-testid="calendar-cell-income" data-figure={`days.${index}.income_forecast`}>
              {formatIncoming(day.income_forecast.value)}
            </span>
            {shown.map((payment) => (
              <span
                key={payment.id}
                className="cal__ev cal__ev--pay"
                aria-hidden="true"
                data-testid="calendar-cell-payment"
                data-source={payment.source}
              >
                <span className="cal__pay-name">{payment.name}</span>
                <span className="cal__pay-sum">{formatOutgoing(payment.amount.value)}</span>
              </span>
            ))}
            {hidden > 0 && (
              <span className="cal__ev cal__ev--more" aria-hidden="true" data-testid="calendar-cell-more">
                {moreLabel(hidden)}
              </span>
            )}
            <span className="cal__bal" aria-hidden="true">
              {red && (
                <span className="cal__badt" data-testid="calendar-cell-badge">
                  {RED_DAY_WORDS}
                </span>
              )}
              <span className="cal__bal-label">остаток</span>
              <span className="cal__bal-sum" data-testid="calendar-cell-closing" data-figure={`days.${index}.closing`}>
                {formatMoney(day.closing.value)}
              </span>
            </span>
          </button>
        )}
      </FigureTip>
    </div>
  )
}

function IdleCell({ cell }: { cell: Extract<GridCell, { kind: 'past' | 'out' }> }) {
  const past = cell.kind === 'past'
  return (
    <div role="gridcell" className={`cal__cell cal__cell--${past ? 'past' : 'out'}`} data-testid={past ? 'calendar-cell-past' : 'calendar-cell-out'}>
      <span className="cal__num">{cell.dayNumber}</span>
      <span className="cal__idle">{past ? 'прошёл' : 'вне окна'}</span>
    </div>
  )
}

/**
 * Monday-first grid of the window (design/components.md, section 24). Past days and days after the window are not buttons.
 * One Tab stop (the selected day); arrows move between days, Enter or Space choose one.
 */
export function CalendarGrid({ days, selectedDate, onSelect, label }: CalendarGridProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [focusedDate, setFocusedDate] = useState<string | null>(null)
  const weeks = useMemo(() => buildGrid(days), [days])
  const stopDate = focusedDate && days.some((day) => day.date === focusedDate) ? focusedDate : selectedDate

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const target = targetIndex(event.key, index, days)
    if (target === null) return
    event.preventDefault()
    const date = days[target]?.date
    if (date) rootRef.current?.querySelector<HTMLButtonElement>(`button[data-cell-date="${date}"]`)?.focus()
  }

  const indexOf = new Map(days.map((day, index) => [day.date, index]))
  return (
    <div className="calwrap" data-testid="calendar-scroll">
      <div className="cal" role="grid" aria-label={label} ref={rootRef} data-testid="calendar-grid">
        <div className="cal__row" role="row">
          {WEEKDAY_HEADERS.map((name) => (
            <div key={name} className="cal__head" role="columnheader">
              {name}
            </div>
          ))}
        </div>
        {weeks.map((week) => (
          <div key={week[0]?.date} className="cal__row" role="row">
            {week.map((cell) => {
              if (cell.kind !== 'day') return <IdleCell key={cell.date} cell={cell} />
              return (
                <DayCell
                  key={cell.date}
                  cell={cell}
                  index={indexOf.get(cell.date) ?? 0}
                  selected={cell.date === selectedDate}
                  tabStop={cell.date === stopDate}
                  onFocusDay={setFocusedDate}
                  onSelect={onSelect}
                  onKeyDown={onKeyDown}
                />
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
