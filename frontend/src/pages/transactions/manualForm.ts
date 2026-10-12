import { parseAmount, type AmountError } from '../../lib/money'
import { formatDateLong } from '../../lib/dates'

export const COMMENT_LIMIT = 200

export type ManualField = 'account' | 'amount' | 'date' | 'comment'

export interface ManualValues {
  accountId: string
  amount: string
  date: string
  comment: string
}

export interface ManualContext {
  /** The calendar date the API calls today. */
  asOf: string
  /** `opening_date` of the chosen account, if known. */
  openingDate: string | null
}

const AMOUNT_TEXT: Record<AmountError, string> = {
  empty: 'Введите сумму',
  not_number: 'Введите сумму цифрами, например 5 400 или 5 400,50',
  zero: 'Сумма должна быть больше нуля',
  decimals: 'Не больше двух знаков после запятой',
  too_large: 'Слишком большая сумма. Проверьте, нет ли лишних нулей',
}

const FUTURE_DATE_TEXT = 'Дата не может быть позже сегодняшней. Плановые платежи появятся в платёжном календаре'

export function openingText(openingDate: string | null): string {
  return openingDate
    ? `Учёт по этому счёту идёт с ${formatDateLong(openingDate)}. Выберите дату не раньше`
    : 'Дата раньше начала учёта по этому счёту'
}

/** Texts of the server reason codes (`error.details.fields`), by API field name. */
export function serverFieldText(field: string, code: string, context: ManualContext): string | null {
  switch (code) {
    case 'required':
      return field === 'date' ? 'Укажите дату' : field === 'amount' ? 'Введите сумму' : 'Выберите счёт'
    case 'must_be_positive':
      return AMOUNT_TEXT.zero
    case 'too_many_decimals':
      return AMOUNT_TEXT.decimals
    case 'too_large':
      return AMOUNT_TEXT.too_large
    case 'in_future':
      return FUTURE_DATE_TEXT
    case 'before_opening':
      return openingText(context.openingDate)
    case 'too_long':
      return 'Не больше 200 знаков'
    default:
      return null
  }
}

/** Server field names are API names; the form calls the account field `account`. */
export function formFieldFor(apiField: string): ManualField | null {
  switch (apiField) {
    case 'account_id':
      return 'account'
    case 'amount':
    case 'date':
    case 'comment':
      return apiField
    default:
      return null
  }
}

export function validateManual(values: ManualValues, context: ManualContext): Partial<Record<ManualField, string>> {
  const errors: Partial<Record<ManualField, string>> = {}
  if (!values.accountId) errors.account = 'Выберите счёт'
  const amount = parseAmount(values.amount)
  if (!amount.ok) errors.amount = AMOUNT_TEXT[amount.error]
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date)) errors.date = 'Укажите дату'
  else if (context.asOf && values.date > context.asOf) errors.date = FUTURE_DATE_TEXT
  else if (context.openingDate && values.date < context.openingDate) errors.date = openingText(context.openingDate)
  if (values.comment.length > COMMENT_LIMIT) errors.comment = 'Не больше 200 знаков'
  return errors
}
