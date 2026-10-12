import { describe, expect, it } from 'vitest'
import { parseAmount } from './money'

const NBSP = String.fromCharCode(160)

describe('parseAmount', () => {
  it.each([
    ['5400', 540000],
    ['5 400', 540000],
    [`5${NBSP}400,5`, 540050],
    ['5400.50', 540050],
    ['0,01', 1],
    ['100000000', 10_000_000_000],
    ['1 640,50', 164050],
  ])('reads "%s" as %d kopecks without floating point', (input, kopecks) => {
    expect(parseAmount(input)).toEqual({ ok: true, kopecks })
  })

  it.each([
    ['', 'empty'],
    ['  ', 'empty'],
    ['abc', 'not_number'],
    ['12,3,4', 'not_number'],
    ['-5', 'not_number'],
    ['0', 'zero'],
    ['0,00', 'zero'],
    ['1,234', 'decimals'],
    ['100000000,01', 'too_large'],
    ['999999999999', 'too_large'],
  ] as const)('rejects "%s" as %s', (input, error) => {
    expect(parseAmount(input)).toEqual({ ok: false, error })
  })

  it('keeps the exactness where a float would not: 0.07 and 1.15', () => {
    expect(parseAmount('0,07')).toEqual({ ok: true, kopecks: 7 })
    expect(parseAmount('1,15')).toEqual({ ok: true, kopecks: 115 })
    expect(parseAmount('19,99')).toEqual({ ok: true, kopecks: 1999 })
  })
})
