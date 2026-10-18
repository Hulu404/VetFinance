import type { RecipeBody, RecipeGroup } from '../../api/types'

// Checks and texts of the recipe form (design/screens/price.md, "Формы"). The server repeats every check; its codes come to the
// same fields. Numbers typed by a person (minutes, percent, quantity) are plain numbers, not money: the client computes nothing.

export const MAX_RECIPE_ITEMS = 30
export const GROUP_OPTIONS: Array<{ id: RecipeGroup; label: string }> = [
  { id: 'drugs', label: 'Препараты' },
  { id: 'anesthesia', label: 'Анестезия' },
  { id: 'supplies', label: 'Расходники' },
]

export interface RecipeRowValues {
  /** Stable key of the row on the screen. */
  key: string
  itemId: string | null
  group: RecipeGroup
  qty: string
}

export interface RecipeValues {
  minutes: string
  doctorPct: string
  rows: RecipeRowValues[]
}

export type RecipeErrors = Record<string, string>

const MINUTES_MAX = 1440
const PCT_MAX = 100
const PCT_DECIMALS = 2
const QTY_DECIMALS = 3

const SERVER_TEXT: Record<string, Record<string, string>> = {
  minutes: { out_of_range: 'От 1 до 1440 минут', invalid: 'Только целое число минут' },
  doctor_pct: {
    out_of_range: 'От 0 до 100%',
    too_many_decimals: 'Не больше двух знаков после запятой',
    invalid: 'Проверьте значение',
  },
  item_id: {
    required: 'Выберите позицию',
    unknown_item: 'Позиции нет на складе',
    duplicate_item: 'Эта позиция уже есть в списке',
    invalid: 'Выберите позицию',
  },
  group: { required: 'Выберите группу', invalid: 'Выберите группу' },
  qty: {
    required: 'Укажите количество',
    must_be_positive: 'Количество должно быть больше нуля',
    too_many_decimals: 'Не больше трёх знаков после запятой',
    invalid: 'Проверьте значение',
    too_large: 'Слишком большое количество',
  },
}

export const UNKNOWN_CODE_TEXT = 'Проверьте значение'

/** "items.2.qty" -> { name: "qty", row: 2 }; "minutes" -> { name: "minutes", row: null }. */
export function splitField(apiField: string): { name: string; row: number | null } {
  const match = /^items\.(\d+)\.(\w+)$/.exec(apiField)
  if (match) return { name: match[2] ?? apiField, row: Number(match[1]) }
  return { name: apiField, row: null }
}

export function recipeServerText(apiField: string, code: string): string {
  const { name } = splitField(apiField)
  return SERVER_TEXT[name]?.[code] ?? UNKNOWN_CODE_TEXT
}

/** Key of an error in `RecipeErrors`: the field name, with the row for the rows of items. */
export function errorKey(name: string, row: number | null): string {
  return row === null ? name : `${name}:${row}`
}

function decimalDigits(text: string): number | null {
  const match = /^\d+(?:[.,](\d+))?$/.exec(text)
  if (!match) return null
  return match[1]?.length ?? 0
}

function toNumber(text: string): number {
  return Number(text.replace(',', '.'))
}

function checkMinutes(text: string, errors: RecipeErrors): number | null {
  const value = text.trim()
  if (value === '') return null
  if (!/^\d+$/.test(value)) {
    errors.minutes = SERVER_TEXT.minutes?.invalid ?? UNKNOWN_CODE_TEXT
    return null
  }
  const minutes = Number(value)
  if (minutes < 1 || minutes > MINUTES_MAX) errors.minutes = SERVER_TEXT.minutes?.out_of_range ?? UNKNOWN_CODE_TEXT
  return minutes
}

function checkPct(text: string, errors: RecipeErrors): number | null {
  const value = text.trim()
  if (value === '') return null
  const digits = decimalDigits(value)
  if (digits === null) {
    errors.doctor_pct = SERVER_TEXT.doctor_pct?.invalid ?? UNKNOWN_CODE_TEXT
    return null
  }
  if (digits > PCT_DECIMALS) errors.doctor_pct = SERVER_TEXT.doctor_pct?.too_many_decimals ?? UNKNOWN_CODE_TEXT
  else if (toNumber(value) > PCT_MAX) errors.doctor_pct = SERVER_TEXT.doctor_pct?.out_of_range ?? UNKNOWN_CODE_TEXT
  return toNumber(value)
}

function checkRow(row: RecipeRowValues, index: number, seen: Set<string>, errors: RecipeErrors): RecipeBody['items'][number] | null {
  const qtyKey = errorKey('qty', index)
  const itemKey = errorKey('item_id', index)
  const qtyText = row.qty.trim()
  if (row.itemId === null) errors[itemKey] = SERVER_TEXT.item_id?.required ?? UNKNOWN_CODE_TEXT
  else if (seen.has(row.itemId)) errors[itemKey] = SERVER_TEXT.item_id?.duplicate_item ?? UNKNOWN_CODE_TEXT
  else seen.add(row.itemId)
  const digits = decimalDigits(qtyText)
  if (qtyText === '') errors[qtyKey] = SERVER_TEXT.qty?.required ?? UNKNOWN_CODE_TEXT
  else if (digits === null) errors[qtyKey] = SERVER_TEXT.qty?.invalid ?? UNKNOWN_CODE_TEXT
  else if (digits > QTY_DECIMALS) errors[qtyKey] = SERVER_TEXT.qty?.too_many_decimals ?? UNKNOWN_CODE_TEXT
  else if (toNumber(qtyText) <= 0) errors[qtyKey] = SERVER_TEXT.qty?.must_be_positive ?? UNKNOWN_CODE_TEXT
  if (errors[itemKey] || errors[qtyKey] || row.itemId === null) return null
  return { item_id: row.itemId, group: row.group, qty: toNumber(qtyText) }
}

export interface RecipeCheck {
  errors: RecipeErrors
  body: RecipeBody | null
}

export function checkRecipe(values: RecipeValues): RecipeCheck {
  const errors: RecipeErrors = {}
  const minutes = checkMinutes(values.minutes, errors)
  const doctorPct = checkPct(values.doctorPct, errors)
  const seen = new Set<string>()
  const items = values.rows.map((row, index) => checkRow(row, index, seen, errors))
  if (Object.keys(errors).length > 0) return { errors, body: null }
  return {
    errors,
    body: { minutes, doctor_pct: doctorPct, items: items.flatMap((item) => (item ? [item] : [])) },
  }
}

/** A number typed back into a field: 0.5 -> "0,5". */
export function numberToInput(value: number | null): string {
  return value === null ? '' : String(value).replace('.', ',')
}
