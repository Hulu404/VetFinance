import { useState } from 'react'
import { useCloseObligation } from '../../api/mutations'
import type { Equipment, Loan } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { InlineAlert } from '../../components/StateBlocks'
import { formatMonthGenitiveYear } from '../../lib/dates'

const FAILED_TEXT = 'Не получилось закрыть. Попробуйте ещё раз.'

const TAIL = 'Прошлые месяцы отчёта не изменятся. Открыть обязательство снова нельзя — его придётся добавить заново.'

/** What closing changes, in the words of the screen: the calendar loses the payments, the report loses the accrual. */
function consequence(item: Loan | Equipment, since: string): string {
  if (item.kind === 'equipment') return `С ${since} его амортизация перестанет попадать в отчёт «Прибыль и убытки». ${TAIL}`
  const accrual = item.kind === 'lease' ? 'платёж по лизингу перестанет' : 'проценты перестанут'
  return `С ${since} его платежи уйдут из календаря, а ${accrual} попадать в отчёт «Прибыль и убытки». ${TAIL}`
}

interface CloseObligationDialogProps {
  item: Loan | Equipment
  /** Month of "today" (`pnl_month.month`): the closing starts from it. */
  month: string
  onClose: () => void
  onClosed: () => void
}

/** The question before closing an obligation: it stays in the list as "закрыт", the past months of the report do not change. */
export function CloseObligationDialog({ item, month, onClose, onClosed }: CloseObligationDialogProps) {
  const close = useCloseObligation()
  const [failed, setFailed] = useState(false)
  const busy = close.isPending
  return (
    <Dialog
      title={`Закрыть «${item.name}»?`}
      subtitle={consequence(item, formatMonthGenitiveYear(month))}
      onClose={onClose}
      busy={busy}
      alert
      testId="obligations-close-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn--danger"
            disabled={busy}
            aria-busy={busy || undefined}
            data-testid="obligations-delete-confirm"
            onClick={() => {
              setFailed(false)
              close.mutate(item.id, { onSuccess: onClosed, onError: () => setFailed(true) })
            }}
          >
            {busy ? 'Закрываем…' : 'Закрыть'}
          </button>
        </>
      }
    >
      {failed && <InlineAlert testId="obligations-close-error">{FAILED_TEXT}</InlineAlert>}
    </Dialog>
  )
}
