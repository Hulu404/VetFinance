import type { CalendarDay, CalendarPayment } from '../api/types'
import { formatDayMonth } from '../lib/dates'
import { formatMoney } from '../lib/format'
import {
  afterWord,
  formatIncoming,
  formatOutgoing,
  isRedDay,
  paymentSourceWord,
  RED_DAY_WORDS,
} from '../lib/planning'
import { FigureButton } from './FigureButton'
import './CalendarList.css'

interface CalendarListProps {
  days: CalendarDay[]
  selectedDate: string | null
  onSelect: (date: string) => void
}

function PaymentLines({ payment, dayIndex, index }: { payment: CalendarPayment; dayIndex: number; index: number }) {
  const after = payment.balance_after.value
  const path = `days.${dayIndex}.payments.${index}`
  return (
    <div className="dayrow__line">
      <span className="dayrow__what">
        <span className="dayrow__name">{payment.name}</span>
        <span className={after < 0 ? 'dayrow__meta dayrow__meta--bad' : 'dayrow__meta'}>
          {paymentSourceWord(payment.source)} · {afterWord(after)}{' '}
          <FigureButton
            figure={payment.balance_after}
            title={`${payment.name} · ${afterWord(after)}`}
            figureKey={`${path}.balance_after`}
            tipValue={formatMoney(after)}
            spokenValue={`${afterWord(after)} ${formatMoney(Math.abs(after))}`}
          >
            {formatMoney(Math.abs(after))}
          </FigureButton>
        </span>
      </span>
      <span className="dayrow__sum dayrow__sum--out">
        <FigureButton
          figure={payment.amount}
          title={payment.name}
          figureKey={`${path}.amount`}
          spokenValue={`${payment.name}, минус ${formatMoney(payment.amount.value)}`}
        >
          {formatOutgoing(payment.amount.value)}
        </FigureButton>
      </span>
    </div>
  )
}

/** The list mode: a row per day with its payments, the balance after each and the evening balance (design/components.md, section 26). */
export function CalendarList({ days, selectedDate, onSelect }: CalendarListProps) {
  return (
    <ul className="daylist" data-testid="calendar-list">
      {days.map((day, dayIndex) => {
        const red = isRedDay(day.status)
        const selected = day.date === selectedDate
        return (
          // The whole row selects the day with the mouse; the keyboard has the date button.
          // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
          <li
            key={day.date}
            className={`dayrow${red ? ' dayrow--bad' : ''}${selected ? ' dayrow--on' : ''}`}
            data-testid="calendar-row"
            data-date={day.date}
            data-status={day.status}
            onClick={(event) => {
              if ((event.target as HTMLElement).closest('button')) return
              onSelect(day.date)
            }}
          >
            <button type="button" className="dayrow__date" aria-pressed={selected} onClick={() => onSelect(day.date)}>
              <span className="dayrow__day">{formatDayMonth(day.date)}</span>
              <span className="dayrow__weekday">{day.weekday}</span>
            </button>
            <div className="dayrow__lines">
              {day.payments.map((payment, index) => (
                <PaymentLines key={payment.id} payment={payment} dayIndex={dayIndex} index={index} />
              ))}
              <div className="dayrow__line">
                <span className="dayrow__what">
                  <span className="dayrow__meta">Выручка, прогноз</span>
                </span>
                <span className="dayrow__sum dayrow__sum--in">
                  <FigureButton
                    figure={day.income_forecast}
                    title="Выручка, прогноз"
                    figureKey={`days.${dayIndex}.income_forecast`}
                    spokenValue={`Выручка, прогноз, плюс ${formatMoney(day.income_forecast.value)}`}
                  >
                    {formatIncoming(day.income_forecast.value)}
                  </FigureButton>
                </span>
              </div>
            </div>
            <div className={red ? 'dayrow__closing dayrow__closing--bad' : 'dayrow__closing'}>
              <span data-testid="calendar-row-closing">
                <FigureButton figure={day.closing} title="Остаток на вечер" figureKey={`days.${dayIndex}.closing`} />
              </span>
              {red && <span className="dayrow__badt">{RED_DAY_WORDS}</span>}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
