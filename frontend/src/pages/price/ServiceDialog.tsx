import { useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useCreateService, useDeleteService, usePatchService } from '../../api/mutations'
import type { ServiceItem } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { Field, type FieldControlProps } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { formatMoney } from '../../lib/format'
import { formatAmountInput } from '../../lib/money'
import {
  changedFields,
  checkService,
  EMPTY_SERVICE,
  FIELD_ORDER,
  serviceServerText,
  type ServiceErrors,
  type ServiceField,
  type ServiceValues,
} from './serviceForm'

const NETWORK_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите'
const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'

export type ServiceDialogTarget =
  | { kind: 'new' }
  | { kind: 'edit'; id: string; values: ServiceValues; priceKopecks: number; priceFromSales: boolean }

interface ServiceDialogProps {
  target: ServiceDialogTarget
  fallbackFocus?: () => void
  onClose: () => void
  onCreated: (item: ServiceItem) => void
  onSaved: () => void
  /** Edit mode: the owner asks to delete the service. */
  onDelete?: () => void
}

export function serviceValuesOf(item: { name: string; group: string | null }, priceKopecks: number): ServiceValues {
  return { name: item.name, group: item.group ?? '', price: formatAmountInput(priceKopecks) }
}

/** "Добавить услугу" and "Изменить услугу" (design/screens/price.md, "Добавить услугу"). */
export function ServiceDialog({ target, fallbackFocus, onClose, onCreated, onSaved, onDelete }: ServiceDialogProps) {
  const editing = target.kind === 'edit'
  const initial = editing ? target.values : EMPTY_SERVICE
  const priceLocked = editing && target.priceFromSales
  const [values, setValues] = useState<ServiceValues>(initial)
  const [errors, setErrors] = useState<ServiceErrors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const create = useCreateService()
  const patch = usePatchService()
  const closeRef = useRef<(() => void) | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)
  const busy = create.isPending || patch.isPending
  const dirty = FIELD_ORDER.some((field) => values[field] !== initial[field])

  const set = (field: ServiceField) => (value: string) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  const focusFirst = (found: ServiceErrors) => {
    const first = FIELD_ORDER.find((field) => found[field])
    if (first) globalThis.setTimeout(() => formRef.current?.querySelector<HTMLElement>(`[data-field="${first}"]`)?.focus(), 0)
  }

  const showServerError = (cause: unknown) => {
    if (!isApiError(cause)) return setGeneral(SERVER_TEXT)
    if (cause.kind === 'network') return setGeneral(NETWORK_TEXT)
    if (cause.kind !== 'validation') return setGeneral(SERVER_TEXT)
    const mapped: ServiceErrors = {}
    for (const [field, code] of Object.entries(cause.fields)) {
      const text = serviceServerText(field, code)
      if (text && (field === 'name' || field === 'group' || field === 'price')) mapped[field] = text
    }
    setErrors(mapped)
    focusFirst(mapped)
    if (Object.keys(mapped).length === 0) setGeneral('Проверьте значение')
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const result = checkService(values, priceLocked)
    setErrors(result.errors)
    if (!result.body) return focusFirst(result.errors)
    if (target.kind === 'new') {
      create.mutate(result.body, { onSuccess: onCreated, onError: showServerError })
      return
    }
    const body = changedFields(result.body, initial, target.priceKopecks, priceLocked)
    if (Object.keys(body).length === 0) return onClose()
    patch.mutate({ id: target.id, body }, { onSuccess: onSaved, onError: showServerError })
  }

  const textField = (field: ServiceField, label: string, optional = false, mode: 'text' | 'decimal' = 'text') => (
    <Field label={label} optional={optional} error={errors[field]} errorTestId={`price-service-field-${field}-error`}>
      {(control: FieldControlProps) => {
        const input = (
          <input {...control} className="input" inputMode={mode} autoComplete="off" value={values[field]} disabled={busy} data-field={field}
            data-testid={`price-service-field-${field}`} onChange={(event) => set(field)(event.target.value)} />
        )
        return field === 'price' ? (
          <div className="amount">
            {input}
            <span className="amount__unit" aria-hidden="true">₽</span>
          </div>
        ) : input
      }}
    </Field>
  )

  return (
    <Dialog
      title={editing ? 'Изменить услугу' : 'Добавить услугу'}
      subtitle={editing ? undefined : 'Услуга появится в прайсе. Чтобы посчитать прибыль, заполните техкарту.'}
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      fallbackFocus={fallbackFocus}
      testId="price-service-dialog"
      footer={
        <>
          {editing && onDelete && (
            <button type="button" className="btn btn--danger price-dialog__delete" disabled={busy} data-testid="price-service-delete" onClick={onDelete}>
              Удалить услугу
            </button>
          )}
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button type="submit" form="service-form" className="btn btn--primary" disabled={busy} aria-busy={busy || undefined} data-testid="price-service-save">
            {busy ? (editing ? 'Сохраняем…' : 'Добавляем…') : editing ? 'Сохранить' : 'Добавить'}
          </button>
        </>
      }
    >
      <form id="service-form" ref={formRef} noValidate onSubmit={submit}>
        {textField('name', 'Название')}
        {textField('group', 'Группа', true)}
        {priceLocked && target.kind === 'edit' ? (
          <p className="fld__hint" data-testid="price-service-price-locked">
            Цена по продажам за 90 дней: {formatMoney(target.priceKopecks)}
          </p>
        ) : (
          <>
            {textField('price', 'Цена, ₽', false, 'decimal')}
            <p className="fld__hint">Если по услуге появятся продажи в Ветменеджере, цену возьмём из них.</p>
          </>
        )}
        {general && <InlineAlert testId="price-service-error">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}

interface DeleteDialogProps {
  id: string
  name: string
  fallbackFocus?: () => void
  onClose: () => void
  onDeleted: () => void
  onMissing: () => void
}

/** The confirmation of the deletion of a manual service. */
export function DeleteServiceDialog({ id, name, fallbackFocus, onClose, onDeleted, onMissing }: DeleteDialogProps) {
  const remove = useDeleteService()
  const [failed, setFailed] = useState<string | null>(null)
  const busy = remove.isPending
  return (
    <Dialog
      title={`Удалить «${name}»?`}
      subtitle="Услуга и её техкарта пропадут из прайса. Продажи в Ветменеджере не изменятся."
      alert
      onClose={onClose}
      busy={busy}
      fallbackFocus={fallbackFocus}
      testId="price-service-delete-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn--danger"
            disabled={busy}
            data-testid="price-service-delete-confirm"
            onClick={() =>
              remove.mutate(id, {
                onSuccess: onDeleted,
                onError: (cause) => {
                  if (isApiError(cause) && cause.kind === 'not_found') return onMissing()
                  setFailed(isApiError(cause) && cause.kind === 'network' ? NETWORK_TEXT : SERVER_TEXT.replace('сохранить', 'удалить'))
                },
              })
            }
          >
            {busy ? 'Удаляем…' : 'Удалить'}
          </button>
        </>
      }
    >
      {failed && <InlineAlert testId="price-service-delete-error">{failed}</InlineAlert>}
    </Dialog>
  )
}

