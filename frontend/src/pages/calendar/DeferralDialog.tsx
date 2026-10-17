import { useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useSetDeferral } from '../../api/mutations'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { deferralServerText, parseDeferral } from './calendarForms'

const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'
const NOT_FOUND_TEXT = 'Контрагент не найден. Обновите страницу.'
const UNKNOWN_TEXT = 'Проверьте значение'

export interface DeferralTarget {
  counterpartyId: string
  counterpartyName: string
  days: number
}

interface DeferralDialogProps {
  target: DeferralTarget
  onClose: () => void
  onSaved: () => void
}

/** The deferral a counterparty allows, in days: the calendar offers to move a payment only within it. */
export function DeferralDialog({ target, onClose, onSaved }: DeferralDialogProps) {
  const save = useSetDeferral()
  const [value, setValue] = useState(String(target.days))
  const [error, setError] = useState<string | null>(null)
  const [general, setGeneral] = useState<string | null>(null)
  const closeRef = useRef<(() => void) | null>(null)
  const busy = save.isPending
  const dirty = value.trim() !== String(target.days)

  const showServerError = (cause: unknown) => {
    if (!isApiError(cause)) return setGeneral(SERVER_TEXT)
    if (cause.kind === 'not_found') return setGeneral(NOT_FOUND_TEXT)
    if (cause.kind === 'validation') {
      const code = cause.fields.max_deferral_days
      return setError((code && deferralServerText(code)) || UNKNOWN_TEXT)
    }
    setGeneral(SERVER_TEXT)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const parsed = parseDeferral(value)
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }
    setError(null)
    save.mutate({ id: target.counterpartyId, days: parsed.days }, { onSuccess: onSaved, onError: showServerError })
  }

  return (
    <Dialog
      title={`Отсрочка для ${target.counterpartyName}`}
      subtitle="Столько дней поставщик готов ждать оплату по договору. Календарь сможет предложить перенести платёж, если из-за него не хватает денег."
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      testId="calendar-deferral-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button
            type="submit"
            form="deferral-form"
            className="btn btn--primary"
            disabled={busy}
            aria-busy={busy || undefined}
            data-testid="calendar-deferral-save"
          >
            {busy ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </>
      }
    >
      <form id="deferral-form" noValidate onSubmit={submit}>
        <Field
          label="Отсрочка, дней"
          error={error}
          errorTestId="calendar-deferral-error"
          hint="0 — платёж не переносим"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              className="input"
              data-testid="calendar-deferral-input"
              data-autofocus
              value={value}
              disabled={busy}
              onChange={(event) => {
                setValue(event.target.value)
                setError(null)
              }}
            />
          )}
        </Field>
        <p className="fld__hint">Действует для всех платежей этого контрагента.</p>
        {general && <InlineAlert testId="calendar-deferral-general">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}
