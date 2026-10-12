import { useSyncExternalStore } from 'react'

/** Subscribes to a CSS media query. Without matchMedia (tests) the query does not match: the wide layout is used. */
export function useMediaQuery(query: string): boolean {
  const subscribe = (callback: () => void) => {
    if (typeof window.matchMedia !== 'function') return () => undefined
    const list = window.matchMedia(query)
    list.addEventListener('change', callback)
    return () => list.removeEventListener('change', callback)
  }
  const getSnapshot = () => (typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : false)
  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}

export const NARROW_LIST_QUERY = '(max-width: 1100px)'
export const MOBILE_QUERY = '(max-width: 820px)'
