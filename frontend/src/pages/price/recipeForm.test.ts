import { describe, expect, it } from 'vitest'
import { checkRecipe, recipeServerText, splitField, type RecipeRowValues } from './recipeForm'

const row = (patch: Partial<RecipeRowValues> = {}): RecipeRowValues => ({ key: 'r1', itemId: 'i1', group: 'drugs', qty: '1', ...patch })

describe('checkRecipe', () => {
  it('builds the body; an empty minutes and percent mean "the clinic average"', () => {
    expect(checkRecipe({ minutes: '', doctorPct: '', rows: [row({ qty: '0,5' })] })).toEqual({
      errors: {},
      body: { minutes: null, doctor_pct: null, items: [{ item_id: 'i1', group: 'drugs', qty: 0.5 }] },
    })
  })

  it('accepts a recipe without items (a service without materials)', () => {
    expect(checkRecipe({ minutes: '18', doctorPct: '30', rows: [] }).body).toEqual({ minutes: 18, doctor_pct: 30, items: [] })
  })

  it('names the mistakes in the words of the screen and sends nothing', () => {
    const result = checkRecipe({ minutes: '2000', doctorPct: '12,345', rows: [row({ itemId: null, qty: '' })] })
    expect(result.body).toBeNull()
    expect(result.errors).toEqual({
      minutes: 'От 1 до 1440 минут',
      doctor_pct: 'Не больше двух знаков после запятой',
      'item_id:0': 'Выберите позицию',
      'qty:0': 'Укажите количество',
    })
  })

  it('refuses a fractional minute, a percent above 100, a zero quantity and a repeated item', () => {
    const result = checkRecipe({ minutes: '1,5', doctorPct: '101', rows: [row({ qty: '0' }), row({ key: 'r2', qty: '1,2345' })] })
    expect(result.errors.minutes).toBe('Только целое число минут')
    expect(result.errors.doctor_pct).toBe('От 0 до 100%')
    expect(result.errors['qty:0']).toBe('Количество должно быть больше нуля')
    expect(result.errors['qty:1']).toBe('Не больше трёх знаков после запятой')
    expect(result.errors['item_id:1']).toBe('Эта позиция уже есть в списке')
  })
})

describe('server codes', () => {
  it('maps the dotted keys of nested fields', () => {
    expect(splitField('items.3.qty')).toEqual({ name: 'qty', row: 3 })
    expect(splitField('minutes')).toEqual({ name: 'minutes', row: null })
    expect(recipeServerText('items.0.item_id', 'unknown_item')).toBe('Позиции нет на складе')
    expect(recipeServerText('doctor_pct', 'whatever')).toBe('Проверьте значение')
  })
})
