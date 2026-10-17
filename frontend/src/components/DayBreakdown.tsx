import type { Ref } from 'react'
import type { CalendarDay, CalendarPayment } from '../api/types'
import { formatDayMonth } from '../lib/dates'
import { formatMoney } from '../lib/format'
import {
  afterWord,
  dayTitle,
  deferralLabel,
  formatIncoming,
  formatOutgoing,
  isRedDay,
  paymentSourceWord,
  RED_DAY_WORDS,
} from '../lib/planning'
import { FigureButton } from './FigureButton'
import { Pill } from './Pill'
import './DayBreakdown.css'

interface DayBreakdownProps {
  day: CalendarDay
  /** Position of the day in `days[]`: the path of `data-figure`. */
  index: number
  headingRef?: Ref<HTMLHeadingElement>
  onEditDeferral: (payment: CalendarPayment) => void
  onDelete: (payment: CalendarPayment) => void
}

interface PaymentRowProps {
  payment: CalendarPayment
  dayIndex: number
  index: number
  onEditDeferral: (payment: CalendarPayment) => void
  onDelete: (payment: CalendarPayment) => void
}

function PaymentRow({ payment, dayIndex, index, onEditDeferral, onDelete }: PaymentRowProps) {
  const short = payment.balance_after.value < 0
  const path = `days.${dayIndex}.payments.${index}`
  const canEditDeferral = payment.source === 'recurring' && payment.counterparty !== null
  return (
    <tr className="dayp__row dayp__row--pay" data-testid="calendar-day-payment" data-source={payment.source} data-payment-id={payment.id}>
      <th scope="row" className="dayp__name">
        <span className="dayp__title">{payment.name}</span>
        <span className="dayp__meta">
          {paymentSourceWord(payment.source)}
          {canEditDeferral && payment.counterparty && (
            <>
              {' · '}
              <button
                type="button"
                className="dayp__link"
                data-testid="calendar-deferral-edit"
                data-payment-id={payment.id}
                data-days={payment.max_deferral_days}
                aria-label={`Отсрочка у контрагента ${payment.counterparty.name}: ${payment.max_deferral_days > 0 ? `${payment.max_deferral_days} дн.` : 'без отсрочки'}. Изменить`}
                onClick={() => onEditDeferral(payment)}
              >
                {deferralLabel(payment.max_deferral_days)}
              </button>
            </>
          )}
          {payment.source === 'manual' && (
            <>
              {' · '}
              <button
                type="button"
                className="dayp__link"
                data-testid="calendar-payment-delete"
                data-payment-id={payment.id}
                aria-label={`Удалить платёж ${payment.name}`}
                onClick={() => onDelete(payment)}
              >
                Удалить
              </button>
            </>
          )}
        </span>
      </th>
      <td className="dayp__sum dayp__sum--out">
        <span data-testid="calendar-day-payment-amount">
          <FigureButton
            figure={payment.amount}
            title={payment.name}
            figureKey={`${path}.amount`}
            spokenValue={`${payment.name}, минус ${formatMoney(payment.amount.value)}`}
          >
            {formatOutgoing(payment.amount.value)}
          </FigureButton>
        </span>
      </td>
      <td className={short ? 'dayp__after dayp__after--short' : 'dayp__after'}>
        <span data-testid="calendar-day-payment-after">
          {afterWord(payment.balance_after.value)}{' '}
          <FigureButton
            figure={payment.balance_after}
            title={`${payment.name} · ${afterWord(payment.balance_after.value)}`}
            figureKey={`${path}.balance_after`}
            tipValue={formatMoney(payment.balance_after.value)}
            spokenValue={`${afterWord(payment.balance_after.value)} ${formatMoney(Math.abs(payment.balance_after.value))}`}
          >
            {formatMoney(Math.abs(payment.balance_after.value))}
          </FigureButton>
        </span>
      </td>
    </tr>
  )
}

/**
 * What a day is made of: the morning balance, the payments with the balance after each, the forecast income, the evening balance
 * and the conclusion of the engine (design/components.md, section 25). Every sum opens its tip.
 */
export function DayBreakdown({ day, index, headingRef, onEditDeferral, onDelete }: DayBreakdownProps) {
  const red = isRedDay(day.status)
  const title = dayTitle(day)
  return (
    <section
      className={red ? 'dayp dayp--bad' : 'dayp'}
      data-testid="calendar-day"
      data-date={day.date}
      data-status={day.status}
      aria-labelledby={`dayp-${day.date}`}
    >
      <h2 className="dayp__label">Разбор дня</h2>
      <div className="dayp__head">
        <h3 id={`dayp-${day.date}`} className="dayp__heading" tabIndex={-1} ref={headingRef} aria-live="polite">
          {title}
        </h3>
        {red && <Pill variant="danger">{RED_DAY_WORDS}</Pill>}
      </div>
      <table className="dayp__table">
        <caption className="sr-only">Разбор дня {formatDayMonth(day.date)}</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Строка</th>
            <th scope="col">Сумма</th>
            <th scope="col">Остаток после платежа</th>
          </tr>
        </thead>
        <tbody>
          <tr className="dayp__row">
            <th scope="row" className="dayp__name">
              <span className="dayp__title">Остаток на утро</span>
            </th>
            <td className="dayp__sum" colSpan={2}>
              <span data-testid="calendar-day-opening">
                <FigureButton figure={day.opening} title="Остаток на утро" figureKey={`days.${index}.opening`} />
              </span>
            </td>
          </tr>
          {day.payments.map((payment, paymentIndex) => (
            <PaymentRow
              key={payment.id}
              payment={payment}
              dayIndex={index}
              index={paymentIndex}
              onEditDeferral={onEditDeferral}
              onDelete={onDelete}
            />
          ))}
          {day.payments.length === 0 && (
            <tr className="dayp__row">
              <th scope="row" className="dayp__name dayp__name--soft" colSpan={3}>
                Платежей нет, ждём только выручку.
              </th>
            </tr>
          )}
          <tr className="dayp__row">
            <th scope="row" className="dayp__name">
              <span className="dayp__title">Выручка, прогноз по средним за 12 недель</span>
            </th>
            <td className="dayp__sum dayp__sum--in" colSpan={2}>
              <span data-testid="calendar-day-income">
                <FigureButton
                  figure={day.income_forecast}
                  title="Выручка, прогноз"
                  figureKey={`days.${index}.income_forecast`}
                  spokenValue={`Выручка, прогноз, плюс ${formatMoney(day.income_forecast.value)}`}
                >
                  {formatIncoming(day.income_forecast.value)}
                </FigureButton>
              </span>
            </td>
          </tr>
          <tr className="dayp__row dayp__row--total">
            <th scope="row" className="dayp__name">
              <span className="dayp__title">Остаток на вечер</span>
            </th>
            <td className={red ? 'dayp__sum dayp__sum--bad' : 'dayp__sum'} colSpan={2}>
              <span data-testid="calendar-day-closing">
                <FigureButton figure={day.closing} title="Остаток на вечер" figureKey={`days.${index}.closing`} />
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <p className={red ? 'dayp__note dayp__note--bad' : 'dayp__note'} data-testid="calendar-day-note">
        {day.note}
      </p>
    </section>
  )
}
