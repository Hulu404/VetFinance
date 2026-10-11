import { describe, expect, it } from 'vitest'
import {
  formatAsOfDate,
  formatByUnit,
  formatClockTime,
  formatDays,
  formatMoney,
  formatPercent,
  sourceLabel,
} from './format'

const NBSP = ' '
const MINUS = '−'

describe('formatMoney', () => {
  it('formats whole rubles with non-breaking spaces', () => {
    expect(formatMoney(41280000)).toBe(`412${NBSP}800${NBSP}₽`)
  })

  it('shows kopecks only when they are not zero', () => {
    expect(formatMoney(228265855)).toBe(`2${NBSP}282${NBSP}658,55${NBSP}₽`)
    expect(formatMoney(41280005)).toBe(`412${NBSP}800,05${NBSP}₽`)
  })

  it('uses the real minus sign for negative amounts', () => {
    expect(formatMoney(-732000)).toBe(`${MINUS}7${NBSP}320${NBSP}₽`)
  })

  it('formats zero and small amounts', () => {
    expect(formatMoney(0)).toBe(`0${NBSP}₽`)
    expect(formatMoney(5)).toBe(`0,05${NBSP}₽`)
    expect(formatMoney(-5)).toBe(`${MINUS}0,05${NBSP}₽`)
  })
})

describe('other units', () => {
  it('formats percent with a comma and one decimal', () => {
    expect(formatPercent(15)).toBe('15,0%')
    expect(formatByUnit(-2.4, 'pct')).toBe(`${MINUS}2,4%`)
  })

  it('declines days', () => {
    expect(formatDays(1)).toBe(`1${NBSP}день`)
    expect(formatDays(3)).toBe(`3${NBSP}дня`)
    expect(formatDays(11)).toBe(`11${NBSP}дней`)
    expect(formatDays(21)).toBe(`21${NBSP}день`)
  })

  it('shows a dash when there is no value', () => {
    expect(formatByUnit(null, 'rub')).toBe('—')
  })

  it('groups counts', () => {
    expect(formatByUnit(12345, 'count')).toBe(`12${NBSP}345`)
  })
})

describe('dates', () => {
  it('formats the report date in Russian without the year suffix', () => {
    expect(formatAsOfDate('2026-09-09')).toBe('9 сентября 2026')
  })

  it('formats the clock time in the clinic time zone', () => {
    expect(formatClockTime('2026-09-09T04:12:00+03:00', 'Europe/Moscow')).toBe('04:12')
    expect(formatClockTime('2026-09-09T01:12:00Z', 'Europe/Moscow')).toBe('04:12')
  })
})

describe('sourceLabel', () => {
  it('maps known sources and keeps unknown ones as is', () => {
    expect(sourceLabel('bank')).toBe('Банк')
    expect(sourceLabel('manual')).toBe('Внесено вручную')
    expect(sourceLabel('something')).toBe('something')
  })
})
