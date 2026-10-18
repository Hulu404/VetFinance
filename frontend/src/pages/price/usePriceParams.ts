import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ServiceFilter, ServiceSort, SortOrder } from '../../api/types'
import { asOfFromSearch } from '../../lib/asOf'

export interface PriceParams {
  /** `?service=<id>`: the opened card. */
  service: string | null
  filter: ServiceFilter
  sort: ServiceSort
  order: SortOrder
  q: string
  /** `?as_of=` goes to the API as is (golden-data checks). */
  asOf: string | null
  update: (patch: Partial<Record<'service' | 'filter' | 'sort' | 'order' | 'q', string | null>>, options?: { replace?: boolean }) => void
}

const DEFAULTS = { filter: 'all', sort: 'margin', order: 'asc' } as const

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.find((candidate) => candidate === value) ?? fallback
}

/** The card, the filter, the sort and the search live in the address (design/screens/price.md, "Раскладка"). */
export function usePriceParams(): PriceParams {
  const [search, setSearch] = useSearchParams()
  const filter = oneOf(search.get('filter'), ['all', 'loss', 'no_recipe'] as const, DEFAULTS.filter)
  const sort = oneOf(search.get('sort'), ['margin', 'profit'] as const, DEFAULTS.sort)
  const order = oneOf(search.get('order'), ['asc', 'desc'] as const, DEFAULTS.order)
  const service = search.get('service') || null
  const q = search.get('q') ?? ''
  const asOf = asOfFromSearch(search.toString())

  const update = useCallback<PriceParams['update']>(
    (patch, options = {}) => {
      setSearch(
        (previous) => {
          const next = new URLSearchParams(previous)
          for (const [name, value] of Object.entries(patch)) {
            const isDefault = value !== null && value !== undefined && name in DEFAULTS && DEFAULTS[name as keyof typeof DEFAULTS] === value
            if (value === null || value === undefined || value === '' || isDefault) next.delete(name)
            else next.set(name, value)
          }
          return next
        },
        { replace: options.replace ?? false },
      )
    },
    [setSearch],
  )

  return { service, filter, sort, order, q, asOf, update }
}
