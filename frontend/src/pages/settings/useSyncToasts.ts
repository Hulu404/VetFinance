import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { invalidateAfterOperationChange } from '../../api/queries'
import type { Connection } from '../../api/types'
import { useToast } from '../../components/Toast'
import { formatCount, pluralRu } from '../../lib/format'
import { syncErrorShort } from '../../lib/syncText'

/** "загружено 24 операции". The number is `counts.value` of the run; only the word form is chosen here. */
function loadedText(count: number): string {
  const noun = pluralRu(count, 'операция', 'операции', 'операций')
  const verb = pluralRu(count, 'загружена', 'загружено', 'загружено')
  return `${verb} ${formatCount(count)} ${noun}`
}

/**
 * Tells how a run ended when the screen saw it running and then finished (design/screens/connections.md, "Синхронизация"),
 * and refreshes lists, totals and the balance, which the run could change.
 */
export function useSyncToasts(connection: Connection | undefined): void {
  const toast = useToast()
  const queryClient = useQueryClient()
  const lastSeen = useRef<{ id: string; status: string } | null>(null)

  const run = connection?.last_run ?? null
  const runId = run?.id ?? null
  const status = run?.status ?? null
  const errorCode = run?.error_code ?? null
  const loaded = run?.counts?.value ?? 0

  useEffect(() => {
    if (runId === null || status === null) return
    const previous = lastSeen.current
    lastSeen.current = { id: runId, status }
    if (!previous || previous.id !== runId || previous.status !== 'running' || status === 'running') return

    if (status === 'success') {
      toast.show({
        message: loaded > 0 ? `Ветменеджер обновлён: ${loadedText(loaded)}.` : 'Ветменеджер обновлён. Новых операций нет.',
      })
    } else if (status === 'partial') {
      toast.show({ message: 'Ветменеджер обновлён не полностью. Подробности в списке запусков ниже.' })
    } else {
      toast.show({ kind: 'error', message: `Не получилось обновить Ветменеджер: ${syncErrorShort(errorCode)}.` })
    }
    void invalidateAfterOperationChange(queryClient)
  }, [runId, status, errorCode, loaded, toast, queryClient])
}
