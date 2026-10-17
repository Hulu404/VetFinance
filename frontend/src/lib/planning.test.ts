import { describe, expect, it } from 'vitest'
import type { CalendarDay } from '../api/types'
import { buildGrid, deferralLabel, moreLabel, paymentsCountText, selectedDate, windowText } from './planning'

function day(date: string, weekday: string, status: CalendarDay['status'] = 'ok'): CalendarDay {
  return { date, weekday, status } as CalendarDay
}

function windowFrom(start: string, weekdays: string[], count: number): CalendarDay[] {
  const [y, m, d] = start.split('-').map(Number) as [number, number, number]
  return Array.from({ length: count }, (_, i) =>
    day(new Date(Date.UTC(y, m - 1, d + i)).toISOString().slice(0, 10), weekdays[i % 7] ?? 'пн'),
  )
}

const plain = (text: string) => text.replace(/\u00a0/g, ' ')
const FROM_WEDNESDAY = ['ср', 'чт', 'пт', 'сб', 'вс', 'пн', 'вт']

describe('buildGrid', () => {
  it('pads a window that starts on Wednesday with two past days and the tail with out-of-window days', () => {
    const weeks = buildGrid(windowFrom('2026-09-09', FROM_WEDNESDAY, 22))
    expect(weeks).toHaveLength(4)
    expect(weeks.every((week) => week.length === 7)).toBe(true)
    expect(weeks[0]?.slice(0, 2).map((cell) => cell.kind)).toEqual(['past', 'past'])
    expect(weeks[0]?.[0]?.date).toBe('2026-09-07')
    expect(weeks[0]?.[2]).toMatchObject({ kind: 'day', today: true })
    const outs = weeks.flat().filter((cell) => cell.kind === 'out')
    expect(outs.map((cell) => cell.date)).toEqual(['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'])
    expect(weeks.flat().filter((cell) => cell.kind === 'day')).toHaveLength(22)
  })

  it('marks the first day of a month so the cell can say "1 окт"', () => {
    const days = windowFrom('2026-09-25', ['пт', 'сб', 'вс', 'пн', 'вт', 'ср', 'чт'], 22)
    const starts = buildGrid(days)
      .flat()
      .filter((cell) => cell.kind === 'day' && cell.monthStart)
    expect(starts.map((cell) => cell.date)).toEqual(['2026-10-01'])
  })

  it('has no padding when the window starts on Monday and ends on Sunday', () => {
    const weeks = buildGrid(windowFrom('2026-10-05', ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'], 21))
    expect(weeks.flat().every((cell) => cell.kind === 'day')).toBe(true)
  })

  it('returns nothing for an empty window', () => {
    expect(buildGrid([])).toEqual([])
  })
})

describe('selectedDate', () => {
  const days = [day('2026-09-09', 'ср'), day('2026-09-10', 'чт'), day('2026-09-11', 'пт', 'below_zero')]

  it('takes the date of the address when it is in the window', () => {
    expect(selectedDate(days, '2026-09-10')).toBe('2026-09-10')
  })

  it('falls back to the first red day, then to the first day', () => {
    expect(selectedDate(days, '2026-12-01')).toBe('2026-09-11')
    expect(selectedDate(days, null)).toBe('2026-09-11')
    expect(selectedDate(days.slice(0, 2), null)).toBe('2026-09-09')
    expect(selectedDate([], null)).toBeNull()
  })
})

describe('words', () => {
  it('declines the count of rows', () => {
    expect(plain(moreLabel(1))).toBe('ещё 1 платёж')
    expect(plain(moreLabel(2))).toBe('ещё 2 платежа')
    expect(plain(moreLabel(5))).toBe('ещё 5 платежей')
    expect(plain(paymentsCountText(15))).toBe('15 платежей')
  })

  it('names the deferral', () => {
    expect(plain(deferralLabel(0))).toBe('без отсрочки')
    expect(plain(deferralLabel(1))).toBe('отсрочка 1 день')
    expect(plain(deferralLabel(3))).toBe('отсрочка 3 дня')
    expect(plain(deferralLabel(5))).toBe('отсрочка 5 дней')
  })

  it('writes the window across the month border and adds the year only when it differs', () => {
    expect(plain(windowText('2026-10-07', '2026-10-28', '2026-10-07'))).toBe('7 октября – 28 октября')
    expect(plain(windowText('2026-12-20', '2027-01-10', '2026-12-20'))).toBe('20 декабря – 10 января 2027')
  })
})
