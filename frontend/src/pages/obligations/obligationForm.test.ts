import { describe, expect, it } from 'vitest'
import { checkObligation, EMPTY_VALUES, obligationFieldFor, obligationServerText, type ObligationValues } from './obligationForm'

const TODAY = '2026-09-09'
const LOAN: ObligationValues = {
  ...EMPTY_VALUES,
  name: 'Кредит на УЗИ',
  lender: 'Сбербанк',
  principal: '940 000',
  remaining: '620 000',
  rate: '12',
  payment: '26 500',
  paymentDay: '10',
}
const EQUIPMENT: ObligationValues = { ...EMPTY_VALUES, name: 'Аппарат УЗИ', cost: '940 800', inServiceFrom: '2025-08-15', lifeYears: '7' }

describe('checkObligation: loan and lease', () => {
  it('builds the loan body in kopecks', () => {
    expect(checkObligation('loan', LOAN, TODAY).body).toEqual({
      kind: 'loan',
      name: 'Кредит на УЗИ',
      lender: 'Сбербанк',
      principal: 94000000,
      remaining: 62000000,
      rate_pct: 12,
      payment: 2650000,
      payment_day: 10,
    })
  })

  it('has no rate and no empty lender in a lease', () => {
    const body = checkObligation('lease', { ...LOAN, lender: '', rate: '' }, TODAY).body
    expect(body).toEqual({ kind: 'lease', name: 'Кредит на УЗИ', principal: 94000000, remaining: 62000000, payment: 2650000, payment_day: 10 })
  })

  it('accepts a paid-off debt (remaining 0) and a rate with two decimals', () => {
    const result = checkObligation('loan', { ...LOAN, remaining: '0', rate: '12,25' }, TODAY)
    expect(result.errors).toEqual({})
    expect(result.body).toMatchObject({ remaining: 0, rate_pct: 12.25 })
  })

  it('names every empty field in the words of the screen and sends nothing', () => {
    const result = checkObligation('loan', EMPTY_VALUES, TODAY)
    expect(result.body).toBeNull()
    expect(result.errors).toEqual({
      name: 'Напишите название, например «Кредит на УЗИ»',
      principal: 'Укажите сумму по договору',
      remaining: 'Укажите остаток',
      rate: 'Укажите ставку',
      payment: 'Укажите платёж',
      payment_day: 'Укажите число месяца',
    })
  })

  it('checks the ranges: the rate, the day of the month, the decimals', () => {
    const result = checkObligation('loan', { ...LOAN, rate: '101', paymentDay: '32', payment: '1,234' }, TODAY)
    expect(result.errors).toEqual({
      rate: 'Ставка от 0 до 100%',
      payment_day: 'Число от 1 до 31',
      payment: 'Не больше двух знаков после запятой',
    })
  })

  it('does not decide whether the payment covers the interest: that is the server', () => {
    expect(checkObligation('loan', { ...LOAN, payment: '100' }, TODAY).errors).toEqual({})
  })
})

describe('checkObligation: equipment', () => {
  it('builds the body', () => {
    expect(checkObligation('equipment', EQUIPMENT, TODAY).body).toEqual({
      kind: 'equipment',
      name: 'Аппарат УЗИ',
      cost: 94080000,
      in_service_from: '2025-08-15',
      life_years: 7,
    })
  })

  it('refuses an empty form, a date in the future and a life of 31 years', () => {
    expect(checkObligation('equipment', EMPTY_VALUES, TODAY).errors).toEqual({
      name: 'Напишите название, например «Аппарат УЗИ»',
      cost: 'Укажите стоимость',
      in_service_from: 'Укажите дату',
      life_years: 'Укажите срок службы',
    })
    const result = checkObligation('equipment', { ...EQUIPMENT, inServiceFrom: '2026-12-01', lifeYears: '31' }, TODAY)
    expect(result.errors).toEqual({ in_service_from: 'Дата не может быть позже сегодняшней', life_years: 'Срок от 1 до 30 лет' })
  })
})

describe('server codes', () => {
  it('maps the codes of the contract to the texts of the screen', () => {
    expect(obligationServerText('loan', 'remaining', 'remaining_gt_principal')).toBe('Остаток не может быть больше суммы по договору')
    expect(obligationServerText('loan', 'rate_pct', 'out_of_range')).toBe('Ставка от 0 до 100%')
    expect(obligationServerText('equipment', 'in_service_from', 'in_future')).toBe('Дата не может быть позже сегодняшней')
    expect(obligationServerText('loan', 'payment_day', 'out_of_range')).toBe('Число от 1 до 31')
    expect(obligationServerText('loan', 'name', 'unheard')).toBeNull()
  })

  it('shows the interest the server gave for a payment below it', () => {
    const text = obligationServerText('loan', 'payment', 'payment_below_interest', 620000)
    expect(text?.replace(/\u00a0/g, ' ')).toBe('Платёж меньше процентов за месяц (6 200 ₽): долг не уменьшится. Проверьте ставку и платёж')
  })

  it('knows which form field an API field belongs to', () => {
    expect(obligationFieldFor('rate_pct')).toBe('rate')
    expect(obligationFieldFor('kind')).toBeNull()
  })
})
