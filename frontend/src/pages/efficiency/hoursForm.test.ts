import { describe, expect, it } from 'vitest'
import { checkHoursForm, doctorKey, initialHours, serverError } from './hoursForm'

const IDS = ['d1', 'd2']

describe('checkHoursForm', () => {
  it('builds the body; an empty doctor field means "not set"', () => {
    const result = checkHoursForm({ minutes: '30', doctors: { d1: '36', d2: '' } }, IDS)
    expect(result.body).toEqual({ avg_visit_minutes: 30, doctors: [{ id: 'd1', hours_per_week: 36 }, { id: 'd2', hours_per_week: null }] })
  })

  it('accepts half hours with a comma', () => {
    expect(checkHoursForm({ minutes: '30', doctors: { d1: '37,5', d2: '0' } }, IDS).body?.doctors).toEqual([
      { id: 'd1', hours_per_week: 37.5 },
      { id: 'd2', hours_per_week: 0 },
    ])
  })

  it('names the mistakes in the words of the screen and sends nothing', () => {
    const result = checkHoursForm({ minutes: '1', doctors: { d1: '81', d2: '10,25' } }, IDS)
    expect(result.body).toBeNull()
    expect(result.errors).toEqual({
      minutes: 'От 5 до 240 минут',
      [doctorKey('d1')]: 'От 0 до 80 часов',
      [doctorKey('d2')]: 'Не больше одного знака после запятой',
    })
  })

  it('requires the minutes and refuses a step other than a half hour', () => {
    expect(checkHoursForm({ minutes: '', doctors: {} }, []).errors.minutes).toBe('Укажите, сколько минут в среднем длится приём')
    expect(checkHoursForm({ minutes: '30', doctors: { d1: '10,3' } }, ['d1']).errors[doctorKey('d1')]).toBe('Проверьте значение')
    expect(checkHoursForm({ minutes: '3,5', doctors: {} }, []).errors.minutes).toBe('Только целое число минут')
  })
})

describe('initialHours and server codes', () => {
  it('writes the hours back into the fields', () => {
    expect(initialHours({ avg_visit_minutes: 30, doctors: [{ id: 'd1', name: 'A', hours_per_week: 37.5 }, { id: 'd2', name: 'B', hours_per_week: null }] })).toEqual({
      minutes: '30',
      doctors: { d1: '37,5', d2: '' },
    })
  })

  it('maps the dotted keys of the doctors to their fields', () => {
    expect(serverError('doctors.1.hours_per_week', 'out_of_range', IDS)).toEqual({ key: doctorKey('d2'), text: 'От 0 до 80 часов' })
    expect(serverError('avg_visit_minutes', 'out_of_range', IDS)).toEqual({ key: 'minutes', text: 'От 5 до 240 минут' })
    expect(serverError('doctors.7.id', 'invalid', IDS)).toBeNull()
  })
})
