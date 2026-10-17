import { describe, expect, it } from 'vitest'
import { checkPayment, parseDeferral, paymentServerText } from './calendarForms'

const WINDOW = { from: '2026-09-09', to: '2026-09-30' }
const VALID = { name: 'Ремонт кондиционера', amount: '18 000', date: '2026-09-15', categoryId: null, deferral: '' }

describe('parseDeferral', () => {
  it('accepts whole days from 0 to 30', () => {
    expect(parseDeferral('0')).toEqual({ ok: true, days: 0 })
    expect(parseDeferral(' 5 ')).toEqual({ ok: true, days: 5 })
    expect(parseDeferral('30')).toEqual({ ok: true, days: 30 })
  })

  it('names the mistake in the words of the screen', () => {
    expect(parseDeferral('')).toEqual({ ok: false, error: 'Укажите число дней, 0 — без отсрочки' })
    expect(parseDeferral('2,5')).toEqual({ ok: false, error: 'Только целое число дней' })
    expect(parseDeferral('-1')).toEqual({ ok: false, error: 'Только целое число дней' })
    expect(parseDeferral('31')).toEqual({ ok: false, error: 'От 0 до 30 дней' })
  })

  it('reads an empty field of the payment form as no deferral', () => {
    expect(parseDeferral('', true)).toEqual({ ok: true, days: 0 })
  })
})

describe('checkPayment', () => {
  it('builds the body in kopecks, with the deferral 0 by default', () => {
    expect(checkPayment(VALID, WINDOW)).toEqual({
      errors: {},
      body: { name: 'Ремонт кондиционера', amount: 1800000, date: '2026-09-15', category_id: null, max_deferral_days: 0 },
    })
  })

  it('collects the mistakes of every field and sends nothing', () => {
    const result = checkPayment({ name: '  ', amount: '', date: '', categoryId: null, deferral: '99' }, WINDOW)
    expect(result.body).toBeNull()
    expect(result.errors).toEqual({
      name: 'Напишите, за что платёж',
      amount: 'Укажите сумму',
      date: 'Укажите дату',
      deferral: 'От 0 до 30 дней',
    })
  })

  it('rejects a date outside the window with the dates of the window', () => {
    const result = checkPayment({ ...VALID, date: '2026-10-05' }, WINDOW)
    expect(result.errors.date?.replace(/\u00a0/g, ' ')).toBe('Дата должна быть в окне календаря: с 9 сентября по 30 сентября')
  })

  it('rejects a name longer than 80 signs and a zero amount', () => {
    const result = checkPayment({ ...VALID, name: 'я'.repeat(81), amount: '0' }, WINDOW)
    expect(result.errors).toMatchObject({ name: 'Не длиннее 80 знаков', amount: 'Сумма должна быть больше нуля' })
  })
})

describe('paymentServerText', () => {
  it('maps the codes of the contract to texts, and does not know the others', () => {
    expect(paymentServerText('amount', 'too_many_decimals', WINDOW)).toBe('Не больше двух знаков после запятой')
    expect(paymentServerText('category_id', 'invalid', WINDOW)).toBe('Такой статьи нет')
    expect(paymentServerText('max_deferral_days', 'out_of_range', WINDOW)).toBe('От 0 до 30 дней')
    expect(paymentServerText('name', 'weird', WINDOW)).toBeNull()
    expect(paymentServerText('unknown_field', 'x', WINDOW)).toBeNull()
  })
})
