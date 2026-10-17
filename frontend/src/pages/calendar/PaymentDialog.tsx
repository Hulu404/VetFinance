import { useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useCreatePayment } from '../../api/mutations'
import { useCategories } from '../../api/queries'
import { CategoryField } from '../../components/CategoryField'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { checkPayment, paymentFieldFor, paymentServerText, type PaymentField, type PaymentWindow } from './calendarForms'

const NETWORK_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите'
const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'
const FIELD_ORDER: PaymentField[] = ['name', 'amount', 'date', 'category', 'deferral']

type Errors = Partial<Record<PaymentField, string>>

interface PaymentDialogProps {
  window: PaymentWindow
  /** The day selected in the calendar: the date of the new payment by default. */
  defaultDate: string
  onClose: () => void
  onCreated: () => void
}

/** A one-off planned payment on a day of the window (no repeats; the owner's decision of 2026-10-16). */
export function PaymentDialog({ window: windowRange, defaultDate, onClose, onCreated }: PaymentDialogProps) {
  const create = useCreatePayment()
  const categories = useCategories()
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(defaultDate)
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [deferral, setDeferral] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const closeRef = useRef<(() => void) | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)
  const busy = create.isPending
  const dirty = name !== '' || amount !== '' || date !== defaultDate || categoryId !== null || deferral !== ''

  const clear = (field: PaymentField) => setErrors((current) => ({ ...current, [field]: undefined }))

  const focusFirst = (found: Errors) => {
    const first = FIELD_ORDER.find((field) => found[field])
    if (!first) return
    globalThis.setTimeout(() => formRef.current?.querySelector<HTMLElement>(`[data-field="${first}"]`)?.focus(), 0)
  }

  const showServerError = (cause: unknown) => {
    if (!isApiError(cause)) return setGeneral(SERVER_TEXT)
    if (cause.kind === 'network') return setGeneral(NETWORK_TEXT)
    if (cause.kind !== 'validation') return setGeneral(SERVER_TEXT)
    const mapped: Errors = {}
    let unknown = false
    for (const [apiField, code] of Object.entries(cause.fields)) {
      const field = paymentFieldFor(apiField)
      const text = field ? paymentServerText(apiField, code, windowRange) : null
      if (field && text) mapped[field] = text
      else unknown = true
    }
    setErrors(mapped)
    focusFirst(mapped)
    if (unknown || Object.keys(mapped).length === 0) setGeneral('Проверьте значение')
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const result = checkPayment({ name, amount, date, categoryId, deferral }, windowRange)
    setErrors(result.errors)
    if (!result.body) {
      focusFirst(result.errors)
      return
    }
    create.mutate(result.body, { onSuccess: onCreated, onError: showServerError })
  }

  return (
    <Dialog
      title="Добавить платёж"
      subtitle="Плановый платёж появится в календаре в выбранный день."
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      testId="calendar-payment-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button
            type="submit"
            form="payment-form"
            className="btn btn--primary"
            disabled={busy}
            aria-busy={busy || undefined}
            data-testid="calendar-payment-save"
          >
            {busy ? 'Добавляем…' : 'Добавить'}
          </button>
        </>
      }
    >
      <form id="payment-form" ref={formRef} noValidate onSubmit={submit}>
        <Field label="Название" error={errors.name} errorTestId="calendar-payment-field-name-error">
          {(control) => (
            <input
              {...control}
              type="text"
              className="input"
              autoComplete="off"
              data-field="name"
              data-testid="calendar-payment-field-name"
              value={name}
              disabled={busy}
              onChange={(event) => {
                setName(event.target.value)
                clear('name')
              }}
            />
          )}
        </Field>
        <div className="fld-row">
          <Field label="Сумма" error={errors.amount} errorTestId="calendar-payment-field-amount-error">
            {(control) => (
              <div className="amount">
                <input
                  {...control}
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  className="input"
                  data-field="amount"
                  data-testid="calendar-payment-field-amount"
                  value={amount}
                  disabled={busy}
                  onChange={(event) => {
                    setAmount(event.target.value)
                    clear('amount')
                  }}
                />
                <span className="amount__unit" aria-hidden="true">
                  ₽
                </span>
              </div>
            )}
          </Field>
          <Field label="Дата" error={errors.date} errorTestId="calendar-payment-field-date-error">
            {(control) => (
              <input
                {...control}
                type="date"
                className="input"
                data-field="date"
                data-testid="calendar-payment-field-date"
                value={date}
                min={windowRange.from}
                max={windowRange.to}
                disabled={busy}
                onChange={(event) => {
                  setDate(event.target.value)
                  clear('date')
                }}
              />
            )}
          </Field>
        </div>
        <div data-field="category" tabIndex={-1} data-testid="calendar-payment-field-category">
          <CategoryField
            label="Статья"
            optional
            categories={categories.data?.items}
            loading={categories.isPending}
            loadError={categories.isError}
            onRetry={() => void categories.refetch()}
            kind="out"
            value={categoryId}
            onChange={(id) => {
              setCategoryId(id)
              clear('category')
            }}
            error={errors.category}
            disabled={busy}
          />
        </div>
        <Field
          label="Отсрочка, дней"
          optional
          error={errors.deferral}
          errorTestId="calendar-payment-field-deferral-error"
          hint="0 — платёж не переносим"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              className="input"
              placeholder="0"
              data-field="deferral"
              data-testid="calendar-payment-field-deferral"
              value={deferral}
              disabled={busy}
              onChange={(event) => {
                setDeferral(event.target.value)
                clear('deferral')
              }}
            />
          )}
        </Field>
        {general && <InlineAlert testId="calendar-payment-error">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}
