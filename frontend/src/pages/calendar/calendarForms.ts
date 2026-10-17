import type { ManualPaymentBody } from '../../api/types'
import { formatDayMonth } from '../../lib/dates'
import { parseAmount, type AmountError } from '../../lib/money'

// Checks and texts of the two forms of the calendar. The server repeats every check; its codes are mapped to the same texts.

export const NAME_LIMIT = 80
export const DEFERRAL_MAX = 30

export const DEFERRAL_TEXT = {
  required: 'Укажите число дней, 0 — без отсрочки',
  invalid: 'Только целое число дней',
  out_of_range: 'От 0 до 30 дней',
} as const

type DeferralCode = keyof typeof DEFERRAL_TEXT

export type DeferralParse = { ok: true; days: number } | { ok: false; error: string }

/** Whole days 0-30. An empty field is a mistake in the deferral dialog and "0" in the payment form (`emptyIsZero`). */
export function parseDeferral(input: string, emptyIsZero = false): DeferralParse {
  const text = input.trim()
  if (text === '') return emptyIsZero ? { ok: true, days: 0 } : { ok: false, error: DEFERRAL_TEXT.required }
  if (!/^\d+$/.test(text)) return { ok: false, error: DEFERRAL_TEXT.invalid }
  const days = Number(text)
  if (days > DEFERRAL_MAX) return { ok: false, error: DEFERRAL_TEXT.out_of_range }
  return { ok: true, days }
}

export function deferralServerText(code: string): string | null {
  return code in DEFERRAL_TEXT ? DEFERRAL_TEXT[code as DeferralCode] : null
}

export type PaymentField = 'name' | 'amount' | 'date' | 'category' | 'deferral'

export interface PaymentValues {
  name: string
  amount: string
  date: string
  categoryId: string | null
  deferral: string
}

export interface PaymentWindow {
  from: string
  to: string
}

const AMOUNT_TEXT: Record<AmountError, string> = {
  empty: 'Укажите сумму',
  not_number: 'Укажите сумму цифрами, например 18 000',
  zero: 'Сумма должна быть больше нуля',
  decimals: 'Не больше двух знаков после запятой',
  too_large: 'Слишком большая сумма',
}

export function outOfWindowText(window: PaymentWindow): string {
  return `Дата должна быть в окне календаря: с ${formatDayMonth(window.from)} по ${formatDayMonth(window.to)}`
}

/** The field of the form that an API field name belongs to (`category_id` is the form's `category`). */
export function paymentFieldFor(apiField: string): PaymentField | null {
  switch (apiField) {
    case 'name':
    case 'amount':
    case 'date':
      return apiField
    case 'category_id':
      return 'category'
    case 'max_deferral_days':
      return 'deferral'
    default:
      return null
  }
}

/** Text for a reason code of the server (`details.fields`), by API field name; null when the code is not known. */
export function paymentServerText(apiField: string, code: string, window: PaymentWindow): string | null {
  switch (apiField) {
    case 'name':
      return code === 'required' ? 'Напишите, за что платёж' : code === 'too_long' ? 'Не длиннее 80 знаков' : null
    case 'amount':
      if (code === 'required') return AMOUNT_TEXT.empty
      if (code === 'must_be_positive') return AMOUNT_TEXT.zero
      if (code === 'too_many_decimals') return AMOUNT_TEXT.decimals
      if (code === 'too_large') return AMOUNT_TEXT.too_large
      return code === 'invalid' ? AMOUNT_TEXT.not_number : null
    case 'date':
      if (code === 'required' || code === 'invalid') return 'Укажите дату'
      return code === 'out_of_window' ? outOfWindowText(window) : null
    case 'category_id':
      return code === 'invalid' ? 'Такой статьи нет' : null
    case 'max_deferral_days':
      return deferralServerText(code)
    default:
      return null
  }
}

export interface PaymentCheck {
  errors: Partial<Record<PaymentField, string>>
  /** The body of `POST /v1/calendar/payments`; null while there are mistakes. */
  body: ManualPaymentBody | null
}

export function checkPayment(values: PaymentValues, window: PaymentWindow): PaymentCheck {
  const errors: Partial<Record<PaymentField, string>> = {}
  const name = values.name.trim()
  if (name === '') errors.name = 'Напишите, за что платёж'
  else if (name.length > NAME_LIMIT) errors.name = 'Не длиннее 80 знаков'
  const amount = parseAmount(values.amount)
  if (!amount.ok) errors.amount = AMOUNT_TEXT[amount.error]
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date)) errors.date = 'Укажите дату'
  else if (values.date < window.from || values.date > window.to) errors.date = outOfWindowText(window)
  const deferral = parseDeferral(values.deferral, true)
  if (!deferral.ok) errors.deferral = deferral.error
  if (Object.keys(errors).length > 0 || !amount.ok || !deferral.ok) return { errors, body: null }
  return {
    errors,
    body: { name, amount: amount.kopecks, date: values.date, category_id: values.categoryId, max_deferral_days: deferral.days },
  }
}
