import { useEffect, useState } from 'react'

export const SLOW_LOADING_MS = 8000

/** True once loading has gone on longer than `SLOW_LOADING_MS`: "Загрузка идёт дольше обычного". */
export function useSlowLoading(loading: boolean): boolean {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!loading) {
      setSlow(false)
      return
    }
    const timer = window.setTimeout(() => setSlow(true), SLOW_LOADING_MS)
    return () => window.clearTimeout(timer)
  }, [loading])
  return slow
}
