import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useReviewDay } from '../../api/mutations'
import { useAcquiringDay } from '../../api/queries'
import type { AcquiringDay, Figure } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { FigureButton } from '../../components/FigureButton'
import { Pill } from '../../components/Pill'
import { InlineAlert } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { formatDateShort, formatDayRangeLong, monthNameLower, monthOf } from '../../lib/dates'
import { formatMoney } from '../../lib/format'
import { reviewedToast, statusView } from './acquiringText'

const NOTE_LIMIT = 200

interface AcquiringDayDialogProps {
  day: AcquiringDay
  coveredTo: string | null
  referenceYear: number | undefined
  onClose: () => void
}

function SumRow({ label, figure }: { label: string; figure: Figure | null }) {
  return (
    <div className="acq-sum">
      <dt>{label}</dt>
      <dd>{figure ? <FigureButton figure={figure} title={label} /> : <span aria-label="нет данных">—</span>}</dd>
    </div>
  )
}

export function AcquiringDayDialog({ day, coveredTo, referenceYear, onClose }: AcquiringDayDialogProps) {
  const details = useAcquiringDay(day.date_from, true)
  const review = useReviewDay()
  const toast = useToast()
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState<string | null>(null)
  const closeRef = useRef<(() => void) | null>(null)

  const view = statusView(day, coveredTo, referenceYear)
  const title = `Сверка за ${formatDayRangeLong(day.date_from, day.date_to)}`
  const canReview = day.status === 'mismatch' && !day.reviewed
  const month = monthOf(day.date_from)

  const submit = () => {
    if (note.length > NOTE_LIMIT) {
      setNoteError('Не больше 200 знаков')
      return
    }
    review.mutate(
      { date: day.date_from, note: note.trim() === '' ? null : note.trim() },
      {
        onSuccess: () => {
          toast.show({ message: reviewedToast(day) })
          onClose()
        },
      },
    )
  }

  const payments = details.data?.payments ?? []
  const credits = details.data?.credits ?? []

  return (
    <Dialog
      title={title}
      wide
      onClose={onClose}
      dirty={note !== ''}
      busy={review.isPending}
      closeRef={closeRef}
      testId="acq-dialog"
      footer={
        <>
          <Link className="btn btn--text acq-open" to={`/transactions?tab=all&month=${month}`} onClick={onClose}>
            Открыть операции за {monthNameLower(month)}
          </Link>
          <button type="button" className="btn" disabled={review.isPending} onClick={() => closeRef.current?.()}>
            {canReview ? 'Отмена' : 'Закрыть'}
          </button>
          {canReview && (
            <button
              type="button"
              className="btn btn--primary"
              disabled={review.isPending}
              aria-busy={review.isPending || undefined}
              data-testid="acq-review"
              onClick={submit}
            >
              {review.isPending ? 'Сохраняем…' : 'Отметить проверенным'}
            </button>
          )}
        </>
      }
    >
      <p className="acq-status">
        <Pill variant={view.pill.variant}>{view.pill.text}</Pill>
        {day.reviewed && <Pill variant="neutral">проверено</Pill>}
        {view.detail && <span>{view.detail}</span>}
      </p>
      <dl className="acq-sums">
        <SumRow label="Оплаты картой" figure={day.card_payments} />
        <SumRow label="Комиссия" figure={day.commission} />
        <SumRow label="Ожидали" figure={day.expected} />
        <SumRow label="Зачислено" figure={day.credited} />
        <SumRow label="Расхождение" figure={day.discrepancy} />
      </dl>

      {details.isPending && <p className="acq-loading" role="status">Загружаем детали дня…</p>}
      {details.isError && (
        <InlineAlert>
          Не получилось загрузить детали дня. Попробуйте ещё раз.
          <button type="button" className="btn btn--text" onClick={() => void details.refetch()}>
            Повторить
          </button>
        </InlineAlert>
      )}
      {details.data && (
        <>
          <h3 className="acq-list-title">Оплаты из Ветменеджера ({payments.length})</h3>
          <ul className="acq-list">
            {payments.map((item, index) => (
              <li key={`${item.description}-${index}`}>
                <span>
                  {item.date ? `${formatDateShort(item.date, referenceYear)} · ` : ''}
                  {item.description}
                </span>
                <span className="acq-list__sum">{formatMoney(item.amount)}</span>
              </li>
            ))}
          </ul>
          <h3 className="acq-list-title">Зачисления банка ({credits.length})</h3>
          {credits.length === 0 ? (
            <p className="acq-empty">Зачислений пока нет.</p>
          ) : (
            <ul className="acq-list">
              {credits.map((item, index) => (
                <li key={`${item.date}-${index}`}>
                  <span>
                    {formatDateShort(item.date, referenceYear)} · {item.description}
                  </span>
                  <span className="acq-list__sum">{formatMoney(item.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {canReview && (
        <Field
          label="Комментарий"
          optional
          error={noteError}
          hint="Например, «комиссия выше обычной, написали в банк». Фамилии клиентов не указывайте."
        >
          {(control) => (
            <textarea
              {...control}
              className="input"
              rows={2}
              value={note}
              disabled={review.isPending}
              onChange={(event) => {
                setNote(event.target.value)
                setNoteError(null)
              }}
            />
          )}
        </Field>
      )}
      {review.isError && <InlineAlert>Не получилось сохранить отметку. Попробуйте ещё раз.</InlineAlert>}
    </Dialog>
  )
}
