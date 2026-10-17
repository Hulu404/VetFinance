import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { isApiError } from '../../api/errors'
import { useCreateObligation, usePatchObligation } from '../../api/mutations'
import type { Equipment, Loan } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { Field, type FieldControlProps } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { Segmented } from '../../components/Tabs'
import { formatAmountInput } from '../../lib/money'
import {
  checkObligation,
  EMPTY_VALUES,
  fieldsOf,
  obligationFieldFor,
  obligationServerText,
  type FormKind,
  type ObligationField,
  type ObligationValues,
} from './obligationForm'

const NETWORK_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите'
const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'
const UNKNOWN_CODE_TEXT = 'Проверьте значение'
const KIND_OPTIONS = [
  { id: 'loan' as const, label: 'Кредит' },
  { id: 'lease' as const, label: 'Лизинг' },
]
type Errors = Partial<Record<ObligationField, string>>

export type ObligationTarget = { kind: 'new'; form: 'loan' | 'equipment' } | { kind: 'edit'; item: Loan | Equipment }

interface ObligationDialogProps {
  target: ObligationTarget
  /** The calendar date the API calls today: a start of work later than it is refused. */
  today: string
  /** Where focus goes when the row of the opener is gone. */
  fallbackFocus?: () => void
  onClose: () => void
  onSaved: (message: string) => void
  /** Edit mode: the owner asks to close the obligation. */
  onCloseObligation?: (item: Loan | Equipment) => void
}

function valuesOf(item: Loan | Equipment): ObligationValues {
  if (item.kind === 'equipment') {
    return { ...EMPTY_VALUES, name: item.name, cost: formatAmountInput(item.cost.value), inServiceFrom: item.in_service_from, lifeYears: String(item.life_years) }
  }
  return {
    ...EMPTY_VALUES,
    name: item.name,
    lender: item.lender ?? '',
    principal: formatAmountInput(item.principal.value),
    remaining: formatAmountInput(item.remaining.value),
    rate: item.rate_pct === null ? '' : String(item.rate_pct).replace('.', ','),
    payment: formatAmountInput(item.payment.value),
    paymentDay: String(item.payment_day),
  }
}

const SAVED_TEXT = { loan: 'Кредит добавлен', lease: 'Лизинг добавлен', equipment: 'Оборудование добавлено' } as const

function titleOf(target: ObligationTarget, kind: FormKind): string {
  if (target.kind === 'edit') return target.item.name
  return kind === 'equipment' ? 'Добавить оборудование' : 'Добавить кредит или лизинг'
}

function subtitleOf(editing: boolean, kind: FormKind): string {
  if (editing) return 'Изменения действуют с текущего месяца. Прошлые месяцы отчёта «Прибыль и убытки» не меняются.'
  return kind === 'equipment'
    ? 'Амортизация войдёт в отчёт «Прибыль и убытки» строкой «Обязательства и амортизация». Со счёта деньги не списываются.'
    : 'Платёж появится в платёжном календаре, проценты или платёж по лизингу — в отчёте «Прибыль и убытки».'
}

interface TextFieldProps {
  field: ObligationField
  label: string
  value: string
  error?: string
  hint?: ReactNode
  optional?: boolean
  mode?: 'text' | 'numeric' | 'decimal'
  money?: boolean
  type?: 'text' | 'date'
  busy: boolean
  onChange: (value: string) => void
}

function TextField({ field, label, value, error, hint, optional, mode = 'text', money = false, type = 'text', busy, onChange }: TextFieldProps) {
  return (
    <Field label={label} optional={optional} error={error} hint={hint} errorTestId={`obligations-field-${field}-error`}>
      {(control: FieldControlProps) => {
        const input = (
          <input
            {...control}
            type={type}
            inputMode={type === 'date' ? undefined : mode}
            autoComplete="off"
            className="input"
            data-field={field}
            data-testid={`obligations-field-${field}`}
            value={value}
            disabled={busy}
            onChange={(event) => onChange(event.target.value)}
          />
        )
        return money ? (
          <div className="amount">
            {input}
            <span className="amount__unit" aria-hidden="true">
              ₽
            </span>
          </div>
        ) : (
          input
        )
      }}
    </Field>
  )
}

/** The form of a loan, a lease or a piece of equipment: adding and changing (design/screens/obligations.md, "Формы"). */
export function ObligationDialog({ target, today, fallbackFocus, onClose, onSaved, onCloseObligation }: ObligationDialogProps) {
  const editing = target.kind === 'edit'
  const initial = editing ? valuesOf(target.item) : EMPTY_VALUES
  const [kind, setKind] = useState<FormKind>(editing ? target.item.kind : target.form)
  const [values, setValues] = useState<ObligationValues>(initial)
  const [errors, setErrors] = useState<Errors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const create = useCreateObligation()
  const patch = usePatchObligation()
  const closeRef = useRef<(() => void) | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)
  const busy = create.isPending || patch.isPending
  const dirty = (Object.keys(initial) as Array<keyof ObligationValues>).some((key) => values[key] !== initial[key]) || (!editing && kind !== target.form)
  const lease = kind === 'lease'

  const set = (key: keyof ObligationValues, field: ObligationField) => (value: string) => {
    setValues((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  const focusFirst = (found: Errors) => {
    const first = fieldsOf(kind).find((field) => found[field])
    if (!first) return
    globalThis.setTimeout(() => formRef.current?.querySelector<HTMLElement>(`[data-field="${first}"]`)?.focus(), 0)
  }

  const showServerError = (cause: unknown) => {
    if (!isApiError(cause)) return setGeneral(SERVER_TEXT)
    if (cause.kind === 'network') return setGeneral(NETWORK_TEXT)
    if (cause.kind !== 'validation') return setGeneral(SERVER_TEXT)
    const interest = typeof cause.details.interest === 'number' ? cause.details.interest : undefined
    const mapped: Errors = {}
    for (const [apiField, code] of Object.entries(cause.fields)) {
      const field = obligationFieldFor(apiField)
      if (field) mapped[field] = obligationServerText(kind, apiField, code, interest) ?? UNKNOWN_CODE_TEXT
    }
    setErrors(mapped)
    focusFirst(mapped)
    if (Object.keys(mapped).length === 0) setGeneral(UNKNOWN_CODE_TEXT)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const result = checkObligation(kind, values, today)
    setErrors(result.errors)
    if (!result.body) {
      focusFirst(result.errors)
      return
    }
    if (target.kind === 'edit') {
      patch.mutate({ id: target.item.id, body: result.body }, { onSuccess: () => onSaved('Изменения сохранены'), onError: showServerError })
    } else {
      create.mutate(result.body, { onSuccess: () => onSaved(SAVED_TEXT[kind]), onError: showServerError })
    }
  }

  const principalLabel = lease ? 'Сумма договора лизинга' : 'Сумма кредита'
  const remainingLabel = lease ? 'Осталось заплатить' : 'Остаток долга на сегодня'

  return (
    <Dialog
      title={titleOf(target, kind)}
      subtitle={subtitleOf(editing, kind)}
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      fallbackFocus={fallbackFocus}
      testId="obligations-dialog"
      footer={
        <>
          {editing && onCloseObligation && (
            <button
              type="button"
              className="btn btn--danger obl-dialog__close"
              disabled={busy}
              data-testid="obligations-delete"
              onClick={() => onCloseObligation(target.item)}
            >
              Закрыть обязательство
            </button>
          )}
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button
            type="submit"
            form="obligation-form"
            className="btn btn--primary"
            disabled={busy}
            aria-busy={busy || undefined}
            data-testid="obligations-save"
          >
            {busy ? (editing ? 'Сохраняем…' : 'Добавляем…') : editing ? 'Сохранить' : 'Добавить'}
          </button>
        </>
      }
    >
      <form id="obligation-form" ref={formRef} noValidate onSubmit={submit}>
        {kind !== 'equipment' && (
          <div className="fld" data-testid="obligations-kind">
            <span className="fld__label" id="obl-kind-label">
              Вид
            </span>
            <Segmented label="Вид" options={KIND_OPTIONS} value={kind} disabled={busy || editing} onChange={setKind} />
            {editing && <p className="fld__hint">Вид не меняется: закройте обязательство и добавьте новое</p>}
          </div>
        )}
        <TextField field="name" label="Название" value={values.name} error={errors.name} busy={busy} onChange={set('name', 'name')} />
        {kind !== 'equipment' && (
          <>
            <TextField
              field="lender"
              label="Банк или лизинговая компания"
              optional
              value={values.lender}
              error={errors.lender}
              busy={busy}
              onChange={set('lender', 'lender')}
            />
            <div className="fld-row">
              <TextField
                field="principal"
                label={principalLabel}
                money
                mode="decimal"
                value={values.principal}
                error={errors.principal}
                hint={lease ? 'Все платежи по договору вместе' : undefined}
                busy={busy}
                onChange={set('principal', 'principal')}
              />
              <TextField
                field="remaining"
                label={remainingLabel}
                money
                mode="decimal"
                value={values.remaining}
                error={errors.remaining}
                busy={busy}
                onChange={set('remaining', 'remaining')}
              />
            </div>
            <div className="fld-row">
              {!lease && (
                <TextField
                  field="rate"
                  label="Ставка, % годовых"
                  mode="decimal"
                  value={values.rate}
                  error={errors.rate}
                  busy={busy}
                  onChange={set('rate', 'rate')}
                />
              )}
              <TextField
                field="payment"
                label="Платёж в месяц"
                money
                mode="decimal"
                value={values.payment}
                error={errors.payment}
                busy={busy}
                onChange={set('payment', 'payment')}
              />
            </div>
            <TextField
              field="payment_day"
              label="День платежа"
              mode="numeric"
              value={values.paymentDay}
              error={errors.payment_day}
              hint="Число месяца; если в месяце нет такого числа — последний день"
              busy={busy}
              onChange={set('paymentDay', 'payment_day')}
            />
          </>
        )}
        {kind === 'equipment' && (
          <>
            <div className="fld-row">
              <TextField
                field="cost"
                label="Стоимость"
                money
                mode="decimal"
                value={values.cost}
                error={errors.cost}
                busy={busy}
                onChange={set('cost', 'cost')}
              />
              <TextField
                field="in_service_from"
                label="Дата ввода в работу"
                type="date"
                value={values.inServiceFrom}
                error={errors.in_service_from}
                busy={busy}
                onChange={set('inServiceFrom', 'in_service_from')}
              />
            </div>
            <TextField
              field="life_years"
              label="Срок службы, лет"
              mode="numeric"
              value={values.lifeYears}
              error={errors.life_years}
              hint="Оборудование в лизинге сюда не вносите: платёж по лизингу уже в расходах."
              busy={busy}
              onChange={set('lifeYears', 'life_years')}
            />
          </>
        )}
        {general && <InlineAlert testId="obligations-error">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}
