import { useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import type { PnlView } from '../../api/types'
import { asOfFromSearch } from '../../lib/asOf'
import { isValidMonth } from '../../lib/dates'

export interface ReportParams {
  /** Valid `?month=` or null: the API then answers with the last closed month. */
  month: string | null
  view: PnlView
  /** `?as_of=` is passed to the API as is (golden-data checks, open month). */
  asOf: string | null
  /** Changes address parameters; a null value removes the parameter. */
  update: (patch: Record<string, string | null>, options?: { replace?: boolean }) => void
}

/** Month, view and `as_of` live in the address (design/screens/pnl.md, "Раскладка"). */
export function useReportParams(): ReportParams {
  const [search, setSearch] = useSearchParams()
  const rawMonth = search.get('month')
  const month = isValidMonth(rawMonth) ? rawMonth : null
  const view: PnlView = search.get('view') === 'direction' ? 'direction' : 'clinic'
  const asOf = asOfFromSearch(search.toString())

  const update = useCallback(
    (patch: Record<string, string | null>, options: { replace?: boolean } = {}) => {
      setSearch(
        (previous) => {
          const next = new URLSearchParams(previous)
          for (const [name, value] of Object.entries(patch)) {
            if (value === null) next.delete(name)
            else next.set(name, value)
          }
          return next
        },
        { replace: options.replace ?? false },
      )
    },
    [setSearch],
  )

  return { month, view, asOf, update }
}

/**
 * Keeps the address honest: without a valid month in it, the month the API chose is written there;
 * a `validation` error on `month` (out of range, in the future) drops the month and asks for the default one.
 */
export function useMonthCorrection(params: ReportParams, answered: string | null, error: unknown): void {
  const { month, update } = params
  const monthRejected = isApiError(error) && error.kind === 'validation' && 'month' in error.fields
  useEffect(() => {
    if (month === null && answered) update({ month: answered }, { replace: true })
  }, [month, answered, update])
  useEffect(() => {
    if (monthRejected && month !== null) update({ month: null }, { replace: true })
  }, [monthRejected, month, update])
}
