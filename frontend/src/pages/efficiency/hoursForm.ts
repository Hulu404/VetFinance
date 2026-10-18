import type { EfficiencySettings, EfficiencySettingsBody } from '../../api/types'

// Checks and texts of the form "Часы приёма" (design/screens/efficiency.md). The server repeats every check.
// Hours and minutes are plain numbers typed by a person, not money; the client adds nothing up.

export const MINUTES_MIN = 5
export const MINUTES_MAX = 240
export const HOURS_MAX = 80

export interface HoursValues {
  minutes: string
  /** Doctor id -> the typed hours per week. */
  doctors: Record<string, string>
}

export type HoursErrors = Record<string, string>

const TEXT = {
  minutesRequired: 'Укажите, сколько минут в среднем длится приём',
  minutesRange: `От ${MINUTES_MIN} до ${MINUTES_MAX} минут`,
  minutesInvalid: 'Только целое число минут',
  hoursRange: `От 0 до ${HOURS_MAX} часов`,
  hoursDecimals: 'Не больше одного знака после запятой',
  hoursInvalid: 'Проверьте значение',
} as const

/** Key of the error of a doctor's field; the same words name the test id of the field. */
export const doctorKey = (id: string): string => `doctor-${id}`

export function initialHours(settings: EfficiencySettings): HoursValues {
  return {
    minutes: String(settings.avg_visit_minutes),
    doctors: Object.fromEntries(settings.doctors.map((doctor) => [doctor.id, doctor.hours_per_week === null ? '' : String(doctor.hours_per_week).replace('.', ',')])),
  }
}

function checkMinutes(text: string): { value: number | null; error?: string } {
  const value = text.trim()
  if (value === '') return { value: null, error: TEXT.minutesRequired }
  if (!/^\d+$/.test(value)) return { value: null, error: TEXT.minutesInvalid }
  const minutes = Number(value)
  return minutes < MINUTES_MIN || minutes > MINUTES_MAX ? { value: null, error: TEXT.minutesRange } : { value: minutes }
}

function checkHours(text: string): { value: number | null; error?: string } {
  const value = text.trim()
  if (value === '') return { value: null }
  const match = /^(\d+)(?:[.,](\d*))?$/.exec(value)
  if (!match) return { value: null, error: TEXT.hoursInvalid }
  if ((match[2] ?? '').length > 1) return { value: null, error: TEXT.hoursDecimals }
  const hours = Number(value.replace(',', '.'))
  if (hours > HOURS_MAX) return { value: null, error: TEXT.hoursRange }
  return Math.round(hours * 2) === hours * 2 ? { value: hours } : { value: null, error: TEXT.hoursInvalid }
}

export interface HoursCheck {
  errors: HoursErrors
  body: EfficiencySettingsBody | null
}

export function checkHoursForm(values: HoursValues, doctorIds: string[]): HoursCheck {
  const errors: HoursErrors = {}
  const minutes = checkMinutes(values.minutes)
  if (minutes.error) errors.minutes = minutes.error
  const doctors = doctorIds.map((id) => {
    const result = checkHours(values.doctors[id] ?? '')
    if (result.error) errors[doctorKey(id)] = result.error
    return { id, hours_per_week: result.value }
  })
  if (Object.keys(errors).length > 0 || minutes.value === null) return { errors, body: null }
  return { errors, body: { avg_visit_minutes: minutes.value, doctors } }
}

const SERVER_TEXT: Record<string, Record<string, string>> = {
  avg_visit_minutes: { required: TEXT.minutesRequired, invalid: TEXT.minutesInvalid, out_of_range: TEXT.minutesRange },
  hours_per_week: { out_of_range: TEXT.hoursRange, too_many_decimals: TEXT.hoursDecimals, invalid: TEXT.hoursInvalid },
}

/** "avg_visit_minutes" -> key "minutes"; "doctors.1.hours_per_week" -> key of the doctor at index 1. */
export function serverError(apiField: string, code: string, doctorIds: string[]): { key: string; text: string } | null {
  if (apiField === 'avg_visit_minutes') return { key: 'minutes', text: SERVER_TEXT.avg_visit_minutes?.[code] ?? TEXT.hoursInvalid }
  const match = /^doctors\.(\d+)\.(\w+)$/.exec(apiField)
  const id = match ? doctorIds[Number(match[1])] : undefined
  if (!match || id === undefined) return null
  return { key: doctorKey(id), text: SERVER_TEXT.hours_per_week?.[code] ?? TEXT.hoursInvalid }
}
