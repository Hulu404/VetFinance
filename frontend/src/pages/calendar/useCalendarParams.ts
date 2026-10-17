import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { asOfFromSearch } from '../../lib/asOf'
import { parseIsoDate } from '../../lib/dates'
import { useMediaQuery } from '../../lib/useMediaQuery'

export type CalendarView = 'month' | 'list'

/** On a phone the list is the default view; the grid is wider than the screen. */
export const PHONE_QUERY = '(max-width: 560px)'

export interface CalendarParams {
  view: CalendarView
  /** `?date=` of a day in the window, or null (the screen then picks the first red day). */
  date: string | null
  /** `?as_of=` goes to the API as is (golden-data checks). */
  asOf: string | null
  setView: (view: CalendarView) => void
  setDate: (date: string) => void
}

function validDate(value: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  return parseIsoDate(value) ? value : null
}

/** The view and the chosen day live in the address: `/planning/calendar?view=month|list&date=2026-09-11`. */
export function useCalendarParams(): CalendarParams {
  const [search, setSearch] = useSearchParams()
  const phone = useMediaQuery(PHONE_QUERY)
  const rawView = search.get('view')
  const view: CalendarView = rawView === 'month' || rawView === 'list' ? rawView : phone ? 'list' : 'month'
  const date = validDate(search.get('date'))
  const asOf = asOfFromSearch(search.toString())

  const change = useCallback(
    (name: string, value: string) => {
      setSearch(
        (previous) => {
          const next = new URLSearchParams(previous)
          next.set(name, value)
          return next
        },
        { replace: true },
      )
    },
    [setSearch],
  )
  const setView = useCallback((next: CalendarView) => change('view', next), [change])
  const setDate = useCallback((next: string) => change('date', next), [change])

  return { view, date, asOf, setView, setDate }
}
