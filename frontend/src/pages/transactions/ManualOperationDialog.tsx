import { useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useCreateTransaction } from '../../api/mutations'
import { useAccounts, useCategories } from '../../api/queries'
import type { Transaction } from '../../api/types'
import { CategoryField } from '../../components/CategoryField'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { Segmented } from '../../components/Tabs'
import { parseAmount } from '../../lib/money'
import {
  formFieldFor,
  serverFieldText,
  validateManual,
  type ManualContext,
  type ManualField,
  type ManualValues,
} from './manualForm'

interface ManualOperationDialogProps {
  asOf: string
  onClose: () => void
  onCreated: (tx: Transaction) => void
}

type Errors = Partial<Record<ManualField, string>>

const NETWORK = 'Нет связи с сервером. Проверьте интернет и повторите'
const SERVER = 'Не получилось сохранить операцию. Попробуйте ещё раз'
const UNKNOWN_FIELD = 'Не получилось сохранить операцию. Проверьте поля и попробуйте ещё раз'
const FIELD_ORDER: ManualField[] = ['account', 'amount', 'date', 'comment']

export function ManualOperationDialog({ asOf, onClose, onCreated }: ManualOperationDialogProps) {
  const accounts = useAccounts()
  const categories = useCategories()
  const create = useCreateTransaction()
  const accountList = accounts.data?.items ?? []
  const onlyAccount = accountList.length === 1 ? accountList[0] : undefined

  const [kind, setKind] = useState<'in' | 'out'>('out')
  const [accountId, setAccountId] = useState('')
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [date, setDate] = useState(asOf)
  const [amount, setAmount] = useState('')
  const [comment, setComment] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const closeRef = useRef<(() => void) | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)

  const effectiveAccountId = accountId || onlyAccount?.id || ''
  const account = accountList.find((item) => item.id === effectiveAccountId) ?? null
  const context: ManualContext = { asOf, openingDate: account?.opening_date ?? null }
  const values: ManualValues = { accountId: effectiveAccountId, amount, date, comment }
  const dirty = amount !== '' || comment !== '' || categoryId !== null || accountId !== '' || kind !== 'out' || date !== asOf

  const clear = (field: ManualField) => setErrors((current) => ({ ...current, [field]: undefined }))

  const focusFirstError = (found: Errors) => {
    const first = FIELD_ORDER.find((field) => found[field])
    if (!first) return
    window.setTimeout(() => {
      formRef.current?.querySelector<HTMLElement>(`[data-field="${first}"]`)?.focus()
    }, 0)
  }

  const showServerError = (error: unknown) => {
    if (!isApiError(error)) return setGeneral(SERVER)
    if (error.kind === 'network') return setGeneral(NETWORK)
    if (error.kind !== 'validation') return setGeneral(SERVER)
    const mapped: Errors = {}
    let unknown = false
    for (const [apiField, code] of Object.entries(error.fields)) {
      const field = formFieldFor(apiField)
      const text = field ? serverFieldText(apiField, code, context) : null
      if (field && text) mapped[field] = text
      else unknown = true
    }
    setErrors(mapped)
    focusFirstError(mapped)
    if (unknown || Object.keys(mapped).length === 0) setGeneral(UNKNOWN_FIELD)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const found = validateManual(values, context)
    setErrors(found)
    const parsed = parseAmount(amount)
    if (Object.keys(found).length > 0 || !parsed.ok) {
      focusFirstError(found)
      return
    }
    create.mutate(
      {
        kind,
        account_id: effectiveAccountId,
        category_id: categoryId,
        date,
        amount: parsed.kopecks,
        comment: comment.trim() === '' ? null : comment.trim(),
      },
      { onSuccess: onCreated, onError: showServerError },
    )
  }

  const busy = create.isPending

  return (
    <Dialog
      title="Новая операция"
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      testId="manual-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button
            type="submit"
            form="manual-form"
            className="btn btn--primary"
            disabled={busy}
            aria-busy={busy || undefined}
            data-testid="manual-save"
          >
            {busy ? 'Сохраняем…' : 'Добавить операцию'}
          </button>
        </>
      }
    >
      <form id="manual-form" ref={formRef} noValidate onSubmit={submit}>
        <div className="fld">
          <Segmented
            label="Тип операции"
            options={[
              { id: 'out', label: 'Расход' },
              { id: 'in', label: 'Доход' },
            ]}
            value={kind}
            disabled={busy}
            onChange={(next) => {
              setKind(next)
              setCategoryId(null)
            }}
          />
        </div>
        <Field label="Счёт" error={errors.account}>
          {(control) => (
            <select
              {...control}
              data-field="account"
              className="input"
              value={effectiveAccountId}
              disabled={busy || accounts.isPending}
              onChange={(event) => {
                setAccountId(event.target.value)
                clear('account')
              }}
            >
              {accounts.isPending ? (
                <option value="">Загружаем…</option>
              ) : (
                <>
                  <option value="" disabled={accountList.length === 1}>
                    Выберите счёт
                  </option>
                  {accountList.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </>
              )}
            </select>
          )}
        </Field>
        <CategoryField
          label="Статья"
          optional
          categories={categories.data?.items}
          loading={categories.isPending}
          loadError={categories.isError}
          onRetry={() => void categories.refetch()}
          kind={kind}
          value={categoryId}
          onChange={setCategoryId}
          disabled={busy}
        />
        <div className="fld-row">
          <Field label="Дата" error={errors.date}>
            {(control) => (
              <input
                {...control}
                data-field="date"
                type="date"
                className="input"
                value={date}
                max={asOf}
                min={account?.opening_date}
                disabled={busy}
                onChange={(event) => {
                  setDate(event.target.value)
                  clear('date')
                }}
              />
            )}
          </Field>
          <Field label="Сумма" error={errors.amount}>
            {(control) => (
              <div className="amount">
                <input
                  {...control}
                  data-field="amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  className="input"
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
        </div>
        <Field
          label="Комментарий"
          optional
          error={errors.comment}
          hint="Например, «Такси за анализами». Фамилии клиентов не указывайте."
        >
          {(control) => (
            <textarea
              {...control}
              data-field="comment"
              className="input"
              rows={2}
              value={comment}
              disabled={busy}
              onChange={(event) => {
                setComment(event.target.value)
                clear('comment')
              }}
            />
          )}
        </Field>
        {general && <InlineAlert testId="manual-error">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}
