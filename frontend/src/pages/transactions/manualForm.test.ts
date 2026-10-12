import { describe, expect, it } from 'vitest'
import { formFieldFor, serverFieldText, validateManual } from './manualForm'

const context = { asOf: '2026-09-09', openingDate: '2026-08-01' }
const valid = { accountId: 'A-bank', amount: '640', date: '2026-09-09', comment: '' }

describe('validateManual', () => {
  it('accepts a correct form', () => {
    expect(validateManual(valid, context)).toEqual({})
  })

  it('names every empty field', () => {
    expect(validateManual({ accountId: '', amount: '', date: '', comment: '' }, context)).toEqual({
      account: 'Выберите счёт',
      amount: 'Введите сумму',
      date: 'Укажите дату',
    })
  })

  it('checks the date against today and the opening date', () => {
    expect(validateManual({ ...valid, date: '2026-09-10' }, context).date).toMatch(/позже сегодняшней/)
    expect(validateManual({ ...valid, date: '2026-07-31' }, context).date).toBe(
      'Учёт по этому счёту идёт с 1 августа 2026. Выберите дату не раньше',
    )
    expect(validateManual({ ...valid, date: '2026-08-01' }, context)).toEqual({})
  })

  it('limits the comment to 200 characters', () => {
    expect(validateManual({ ...valid, comment: 'я'.repeat(200) }, context)).toEqual({})
    expect(validateManual({ ...valid, comment: 'я'.repeat(201) }, context).comment).toBe('Не больше 200 знаков')
  })

  it('does not block on the date when today is unknown', () => {
    expect(validateManual(valid, { asOf: '', openingDate: null })).toEqual({})
  })
})

describe('server reasons', () => {
  it('maps the codes of the contract to the texts of the spec', () => {
    expect(serverFieldText('amount', 'must_be_positive', context)).toBe('Сумма должна быть больше нуля')
    expect(serverFieldText('amount', 'too_many_decimals', context)).toBe('Не больше двух знаков после запятой')
    expect(serverFieldText('date', 'before_opening', context)).toMatch(/1 августа 2026/)
    expect(serverFieldText('comment', 'too_long', context)).toBe('Не больше 200 знаков')
    expect(serverFieldText('amount', 'something_new', context)).toBeNull()
  })

  it('knows the form fields', () => {
    expect(formFieldFor('account_id')).toBe('account')
    expect(formFieldFor('amount')).toBe('amount')
    expect(formFieldFor('kind')).toBeNull()
  })
})
