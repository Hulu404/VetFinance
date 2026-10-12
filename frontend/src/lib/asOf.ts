import { parseIsoDate } from './dates'

/**
 * The `?as_of=YYYY-MM-DD` address parameter: the reference date of the dashboard, passed to `GET /v1/dashboard`
 * as is (needed to compare the screen with the golden data on a fixed date). Anything that is not a date is ignored.
 */
export function asOfFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get('as_of')
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  return parseIsoDate(value) ? value : null
}
