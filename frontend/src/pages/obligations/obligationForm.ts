import type { ObligationBody } from '../../api/types'
import { formatMoney } from '../../lib/format'
import { parseAmount, type AmountError } from '../../lib/money'

// Checks and texts of the obligation forms (design/screens/obligations.md, "Формы"). The server repeats every check and adds the
// ones that need a calculation (the interest of the month): its codes come to the same fields. The client calculates nothing.

export type FormKind = 'loan' | 'lease' | 'equipment'
export type ObligationField =
  | 'name'
  | 'lender'
  | 'principal'
  | 'remaining'
  | 'rate'
  | 'payment'
  | 'payment_day'
  | 'cost'
  | 'in_service_from'
  | 'life_years'

export interface ObligationValues {
  name: string
  lender: string
  principal: string
  remaining: string
  rate: string
  payment: string
  paymentDay: string
  cost: string
  inServiceFrom: string
  lifeYears: string
}

export const EMPTY_VALUES: ObligationValues = {
  name: '',
  lender: '',
  principal: '',
  remaining: '',
  rate: '',
  payment: '',
  paymentDay: '',
  cost: '',
  inServiceFrom: '',
  lifeYears: '',
}

export const NAME_LIMIT = 80
const RATE_MAX = 100
const DAY_MAX = 31
const YEARS_MAX = 30
const FIELD_NAMES: Record<string, ObligationField> = {
  name: 'name',
  lender: 'lender',
  principal: 'principal',
  remaining: 'remaining',
  rate_pct: 'rate',
  payment: 'payment',
  payment_day: 'payment_day',
  cost: 'cost',
  in_service_from: 'in_service_from',
  life_years: 'life_years',
}

/** The form field an API field belongs to (`rate_pct` is the field "rate"). */
export function obligationFieldFor(apiField: string): ObligationField | null {
  return FIELD_NAMES[apiField] ?? null
}

/** Fields of a kind in the order of the form (focus goes to the first one with a mistake). */
export function fieldsOf(kind: FormKind): ObligationField[] {
  return kind === 'equipment'
    ? ['name', 'cost', 'in_service_from', 'life_years']
    : kind === 'loan'
      ? ['name', 'lender', 'principal', 'remaining', 'rate', 'payment', 'payment_day']
      : ['name', 'lender', 'principal', 'remaining', 'payment', 'payment_day']
}

type Errors = Partial<Record<ObligationField, string>>

const NAME_REQUIRED: Record<FormKind, string> = {
  loan: 'Напишите название, например «Кредит на УЗИ»',
  lease: 'Напишите название, например «Лизинг рентгена»',
  equipment: 'Напишите название, например «Аппарат УЗИ»',
}

function amountText(error: AmountError, required: string, zeroText: string): string {
  switch (error) {
    case 'empty':
      return required
    case 'not_number':
      return 'Введите сумму цифрами, например 940 000'
    case 'zero':
      return zeroText
    case 'decimals':
      return 'Не больше двух знаков после запятой'
    default:
      return 'Слишком большая сумма'
  }
}

/** Text for a reason code of the server (`details.fields`) of an API field; null when the code is not known. */
export function obligationServerText(kind: FormKind, apiField: string, code: string, interest?: number): string | null {
  const common: Record<string, string> = {
    too_many_decimals: 'Не больше двух знаков после запятой',
    too_large: 'Слишком большая сумма',
    invalid: 'Введите значение цифрами',
  }
  switch (apiField) {
    case 'name':
      return code === 'required' ? NAME_REQUIRED[kind] : code === 'too_long' ? 'Не длиннее 80 знаков' : null
    case 'lender':
      return code === 'too_long' ? 'Не длиннее 80 знаков' : null
    case 'principal':
    case 'cost': {
      const required = apiField === 'cost' ? 'Укажите стоимость' : 'Укажите сумму по договору'
      return code === 'required' ? required : code === 'must_be_positive' ? 'Сумма должна быть больше нуля' : (common[code] ?? null)
    }
    case 'remaining':
      if (code === 'required') return 'Укажите остаток'
      return code === 'remaining_gt_principal' ? 'Остаток не может быть больше суммы по договору' : (common[code] ?? null)
    case 'rate_pct':
      if (code === 'required') return 'Укажите ставку'
      return code === 'out_of_range' ? 'Ставка от 0 до 100%' : code === 'too_many_decimals' ? common.too_many_decimals! : null
    case 'payment':
      if (code === 'required') return 'Укажите платёж'
      if (code === 'must_be_positive') return 'Платёж должен быть больше нуля'
      if (code === 'payment_below_interest') {
        return interest === undefined
          ? 'Платёж меньше процентов за месяц: долг не уменьшится. Проверьте ставку и платёж'
          : `Платёж меньше процентов за месяц (${formatMoney(interest)}): долг не уменьшится. Проверьте ставку и платёж`
      }
      return common[code] ?? null
    case 'payment_day':
      return code === 'required' ? 'Укажите число месяца' : code === 'out_of_range' ? 'Число от 1 до 31' : null
    case 'in_service_from':
      if (code === 'required' || code === 'invalid') return 'Укажите дату'
      return code === 'in_future' ? 'Дата не может быть позже сегодняшней' : null
    case 'life_years':
      return code === 'required' ? 'Укажите срок службы' : code === 'out_of_range' || code === 'invalid' ? 'Срок от 1 до 30 лет' : null
    default:
      return null
  }
}

function wholeNumber(text: string, min: number, max: number): number | null {
  const value = text.trim()
  if (!/^\d+$/.test(value)) return null
  const number = Number(value)
  return number >= min && number <= max ? number : null
}

/** Rate in percent per year with up to two decimals: an input of the owner, not a calculation. */
function parseRate(text: string): { ok: true; value: number } | { ok: false; error: string } {
  const value = text.trim().replace(',', '.')
  if (value === '') return { ok: false, error: 'Укажите ставку' }
  if (!/^\d+(\.\d*)?$/.test(value)) return { ok: false, error: 'Ставка от 0 до 100%' }
  const [, fraction = ''] = value.split('.')
  if (fraction.length > 2) return { ok: false, error: 'Не больше двух знаков после запятой' }
  const rate = Number(value)
  return rate > RATE_MAX ? { ok: false, error: 'Ставка от 0 до 100%' } : { ok: true, value: rate }
}

export interface ObligationCheck {
  errors: Errors
  /** The body of `POST` and `PATCH`; null while there are mistakes. */
  body: ObligationBody | null
}

function checkEquipment(values: ObligationValues, today: string, errors: Errors): ObligationBody | null {
  const cost = parseAmount(values.cost)
  if (!cost.ok) errors.cost = amountText(cost.error, 'Укажите стоимость', 'Сумма должна быть больше нуля')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.inServiceFrom)) errors.in_service_from = 'Укажите дату'
  else if (values.inServiceFrom > today) errors.in_service_from = 'Дата не может быть позже сегодняшней'
  const years = wholeNumber(values.lifeYears, 1, YEARS_MAX)
  if (values.lifeYears.trim() === '') errors.life_years = 'Укажите срок службы'
  else if (years === null) errors.life_years = 'Срок от 1 до 30 лет'
  if (!cost.ok || years === null || errors.in_service_from) return null
  return { kind: 'equipment', name: values.name.trim(), cost: cost.kopecks, in_service_from: values.inServiceFrom, life_years: years }
}

function checkLoan(kind: 'loan' | 'lease', values: ObligationValues, errors: Errors): ObligationBody | null {
  const principal = parseAmount(values.principal)
  if (!principal.ok) errors.principal = amountText(principal.error, 'Укажите сумму по договору', 'Сумма должна быть больше нуля')
  const remaining = parseAmount(values.remaining, { allowZero: true })
  if (!remaining.ok) errors.remaining = amountText(remaining.error, 'Укажите остаток', 'Укажите остаток')
  const payment = parseAmount(values.payment)
  if (!payment.ok) errors.payment = amountText(payment.error, 'Укажите платёж', 'Платёж должен быть больше нуля')
  const rate = kind === 'loan' ? parseRate(values.rate) : ({ ok: true, value: 0 } as const)
  if (!rate.ok) errors.rate = rate.error
  const day = wholeNumber(values.paymentDay, 1, DAY_MAX)
  if (values.paymentDay.trim() === '') errors.payment_day = 'Укажите число месяца'
  else if (day === null) errors.payment_day = 'Число от 1 до 31'
  if (!principal.ok || !remaining.ok || !payment.ok || !rate.ok || day === null) return null
  const lender = values.lender.trim()
  const common = {
    name: values.name.trim(),
    ...(lender === '' ? {} : { lender }),
    principal: principal.kopecks,
    remaining: remaining.kopecks,
    payment: payment.kopecks,
    payment_day: day,
  }
  return kind === 'loan' ? { kind, ...common, rate_pct: rate.value } : { kind, ...common }
}

export function checkObligation(kind: FormKind, values: ObligationValues, today: string): ObligationCheck {
  const errors: Errors = {}
  const name = values.name.trim()
  if (name === '') errors.name = NAME_REQUIRED[kind]
  else if (name.length > NAME_LIMIT) errors.name = 'Не длиннее 80 знаков'
  if (kind !== 'equipment' && values.lender.trim().length > NAME_LIMIT) errors.lender = 'Не длиннее 80 знаков'
  const body = kind === 'equipment' ? checkEquipment(values, today, errors) : checkLoan(kind, values, errors)
  return { errors, body: Object.keys(errors).length > 0 ? null : body }
}
