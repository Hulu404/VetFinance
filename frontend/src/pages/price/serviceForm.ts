import type { ServiceBody, ServicePatchBody } from '../../api/types'
import { parseAmount, type AmountError } from '../../lib/money'

// Checks and texts of the form "Добавить услугу" (design/screens/price.md). The server repeats every check.

export type ServiceField = 'name' | 'group' | 'price'
export type ServiceErrors = Partial<Record<ServiceField, string>>

export interface ServiceValues {
  name: string
  group: string
  price: string
}

export const EMPTY_SERVICE: ServiceValues = { name: '', group: '', price: '' }
export const NAME_LIMIT = 120
export const GROUP_LIMIT = 80
export const FIELD_ORDER: ServiceField[] = ['name', 'group', 'price']

const PRICE_TEXT: Record<AmountError, string> = {
  empty: 'Укажите цену',
  not_number: 'Проверьте значение',
  zero: 'Цена должна быть больше нуля',
  decimals: 'Не больше двух знаков после запятой',
  too_large: 'Слишком большая сумма',
}

const SERVER_TEXT: Record<ServiceField, Record<string, string>> = {
  name: {
    required: 'Напишите название услуги',
    too_long: 'Не длиннее 120 знаков',
    duplicate_name: 'Такая услуга уже есть',
  },
  group: { too_long: 'Не длиннее 80 знаков' },
  price: {
    required: 'Укажите цену',
    invalid: 'Проверьте значение',
    must_be_positive: 'Цена должна быть больше нуля',
    too_many_decimals: 'Не больше двух знаков после запятой',
    too_large: 'Слишком большая сумма',
  },
}

export function serviceServerText(field: string, code: string): string | null {
  if (field !== 'name' && field !== 'group' && field !== 'price') return null
  return SERVER_TEXT[field][code] ?? 'Проверьте значение'
}

export interface ServiceCheck {
  errors: ServiceErrors
  body: ServiceBody | null
}

/** `priceLocked`: the price comes from the sales and is not sent (read-only in the form). */
export function checkService(values: ServiceValues, priceLocked = false): ServiceCheck {
  const errors: ServiceErrors = {}
  const name = values.name.trim()
  const group = values.group.trim()
  if (name === '') errors.name = SERVER_TEXT.name.required
  else if (name.length > NAME_LIMIT) errors.name = SERVER_TEXT.name.too_long
  if (group.length > GROUP_LIMIT) errors.group = SERVER_TEXT.group.too_long
  let kopecks = 0
  if (!priceLocked) {
    const price = parseAmount(values.price)
    if (price.ok) kopecks = price.kopecks
    else errors.price = PRICE_TEXT[price.error]
  }
  if (Object.keys(errors).length > 0) return { errors, body: null }
  return { errors, body: { name, ...(group === '' ? {} : { group }), price: kopecks } }
}

/** The fields that changed: `PATCH` takes any subset. An emptied group is sent as an empty string. */
export function changedFields(body: ServiceBody, initial: ServiceValues, initialPrice: number, priceLocked: boolean): ServicePatchBody {
  const patch: ServicePatchBody = {}
  if (body.name !== initial.name.trim()) patch.name = body.name
  if ((body.group ?? '') !== initial.group.trim()) patch.group = body.group ?? ''
  if (!priceLocked && body.price !== initialPrice) patch.price = body.price
  return patch
}
