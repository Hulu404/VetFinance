import { useMemo, useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useSaveRecipe } from '../../api/mutations'
import { useServiceRecipe, useStockItems } from '../../api/queries'
import type { RecipeGroup, ServiceRecipe, StockItem } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { Field, type FieldControlProps } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { Segmented } from '../../components/Tabs'
import { formatFigure } from '../../lib/format'
import { MOBILE_QUERY, useMediaQuery } from '../../lib/useMediaQuery'
import { StockItemField } from './StockItemField'
import {
  checkRecipe,
  errorKey,
  GROUP_OPTIONS,
  MAX_RECIPE_ITEMS,
  numberToInput,
  recipeServerText,
  splitField,
  UNKNOWN_CODE_TEXT,
  type RecipeErrors,
  type RecipeRowValues,
  type RecipeValues,
} from './recipeForm'

const NETWORK_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите'
const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'
const NO_VALUE = '—'

export interface RecipeTarget {
  id: string
  name: string
}

interface RecipeDialogProps {
  target: RecipeTarget
  fallbackFocus?: () => void
  onClose: () => void
  onSaved: () => void
}

/** Opens the dialog at once; the form appears when the recipe has come. */
export function RecipeDialog({ target, fallbackFocus, onClose, onSaved }: RecipeDialogProps) {
  const recipe = useServiceRecipe(target.id)
  const stock = useStockItems()
  const title = `Техкарта: ${target.name}`
  const subtitle = 'Что и сколько уходит на одну услугу. Цену позиции берём со склада.'
  if (recipe.data) {
    return <RecipeForm target={target} recipe={recipe.data} stockItems={stock.data?.items} stockLoading={stock.isPending} stockError={stock.isError} onRetryStock={() => void stock.refetch()} title={title} subtitle={subtitle} fallbackFocus={fallbackFocus} onClose={onClose} onSaved={onSaved} />
  }
  return (
    <Dialog title={title} subtitle={subtitle} wide onClose={onClose} fallbackFocus={fallbackFocus} testId="price-recipe-dialog">
      {recipe.isError ? (
        <InlineAlert testId="price-recipe-load-error">
          {isApiError(recipe.error) && recipe.error.kind === 'network' ? NETWORK_TEXT : 'Не получилось загрузить техкарту.'}{' '}
          <button type="button" className="btn btn--text" onClick={() => void recipe.refetch()}>
            Повторить
          </button>
        </InlineAlert>
      ) : (
        <p role="status">Загружаем техкарту…</p>
      )}
    </Dialog>
  )
}

interface FormProps {
  target: RecipeTarget
  recipe: ServiceRecipe
  stockItems: StockItem[] | undefined
  stockLoading: boolean
  stockError: boolean
  onRetryStock: () => void
  title: string
  subtitle: string
  fallbackFocus?: () => void
  onClose: () => void
  onSaved: () => void
}

let rowCounter = 0
const nextKey = () => `row-${(rowCounter += 1)}`

function initialValues(recipe: ServiceRecipe): RecipeValues {
  return {
    minutes: numberToInput(recipe.minutes),
    doctorPct: numberToInput(recipe.doctor_pct),
    rows: recipe.items.map((item) => ({ key: nextKey(), itemId: item.item_id, group: item.group, qty: numberToInput(item.qty) })),
  }
}

function sameValues(left: RecipeValues, right: RecipeValues): boolean {
  return (
    left.minutes === right.minutes &&
    left.doctorPct === right.doctorPct &&
    left.rows.length === right.rows.length &&
    left.rows.every((row, index) => row.itemId === right.rows[index]?.itemId && row.group === right.rows[index]?.group && row.qty === right.rows[index]?.qty)
  )
}

function RecipeForm({ target, recipe, stockItems, stockLoading, stockError, onRetryStock, title, subtitle, fallbackFocus, onClose, onSaved }: FormProps) {
  const initial = useMemo(() => initialValues(recipe), [recipe])
  const [values, setValues] = useState<RecipeValues>(initial)
  const [errors, setErrors] = useState<RecipeErrors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const save = useSaveRecipe()
  const closeRef = useRef<(() => void) | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)
  const phone = useMediaQuery(MOBILE_QUERY)
  const busy = save.isPending
  const dirty = !sameValues(values, initial)

  // The warehouse list plus the items already in the recipe (the recipe knows their names even when the page of the list does not).
  const catalog = useMemo(() => {
    const byId = new Map<string, StockItem>()
    for (const item of recipe.items) byId.set(item.item_id, { id: item.item_id, name: item.name, unit: item.unit, unit_cost: item.unit_cost })
    for (const item of stockItems ?? []) byId.set(item.id, item)
    return [...byId.values()]
  }, [recipe.items, stockItems])

  const clearError = (key: string) => setErrors((current) => ({ ...current, [key]: '' }))
  const patchRow = (key: string, patch: Partial<RecipeRowValues>, errorField: string, index: number) => {
    setValues((current) => ({ ...current, rows: current.rows.map((row) => (row.key === key ? { ...row, ...patch } : row)) }))
    clearError(errorKey(errorField, index))
  }

  const focusFirst = (found: RecipeErrors) => {
    const first = Object.keys(found).find((key) => found[key])
    if (!first) return
    globalThis.setTimeout(() => formRef.current?.querySelector<HTMLElement>(`[data-error-key="${first}"]`)?.focus(), 0)
  }

  const showServerError = (cause: unknown) => {
    if (!isApiError(cause)) return setGeneral(SERVER_TEXT)
    if (cause.kind === 'network') return setGeneral(NETWORK_TEXT)
    if (cause.kind !== 'validation') return setGeneral(SERVER_TEXT)
    const mapped: RecipeErrors = {}
    for (const [apiField, code] of Object.entries(cause.fields)) {
      const { name, row } = splitField(apiField)
      mapped[errorKey(name, row)] = recipeServerText(apiField, code)
    }
    setErrors(mapped)
    focusFirst(mapped)
    if (Object.keys(mapped).length === 0 || 'items' in mapped) setGeneral(mapped.items ?? UNKNOWN_CODE_TEXT)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const result = checkRecipe(values)
    setErrors(result.errors)
    if (!result.body) return focusFirst(result.errors)
    save.mutate({ id: target.id, body: result.body }, { onSuccess: onSaved, onError: showServerError })
  }

  const addRow = () => setValues((current) => ({ ...current, rows: [...current.rows, { key: nextKey(), itemId: null, group: 'drugs', qty: '' }] }))
  const removeRow = (key: string) => setValues((current) => ({ ...current, rows: current.rows.filter((row) => row.key !== key) }))

  return (
    <Dialog
      title={title}
      subtitle={subtitle}
      wide
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      fallbackFocus={fallbackFocus}
      testId="price-recipe-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button type="submit" form="recipe-form" className="btn btn--primary" disabled={busy} aria-busy={busy || undefined} data-testid="price-recipe-save">
            {busy ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </>
      }
    >
      <form id="recipe-form" ref={formRef} noValidate onSubmit={submit}>
        <div className="fld-row">
          <Field
            label="Время услуги в кабинете, минут"
            optional
            error={errors.minutes}
            errorTestId="price-recipe-field-minutes-error"
            hint={`Пусто — возьмём среднюю по клинике: ${formatFigure(recipe.defaults.minutes)} мин`}
          >
            {(control: FieldControlProps) => (
              <input {...control} className="input" inputMode="numeric" autoComplete="off" value={values.minutes} disabled={busy} data-error-key="minutes" data-testid="price-recipe-field-minutes"
                onChange={(event) => { setValues({ ...values, minutes: event.target.value }); clearError('minutes') }} />
            )}
          </Field>
          <Field
            label="Процент врачу от цены, %"
            optional
            error={errors.doctor_pct}
            errorTestId="price-recipe-field-doctor_pct-error"
            hint={`Пусто — возьмём средний по клинике: ${recipe.defaults.doctor_pct ? formatFigure(recipe.defaults.doctor_pct) : NO_VALUE}`}
          >
            {(control: FieldControlProps) => (
              <input {...control} className="input" inputMode="decimal" autoComplete="off" value={values.doctorPct} disabled={busy} data-error-key="doctor_pct" data-testid="price-recipe-field-doctor_pct"
                onChange={(event) => { setValues({ ...values, doctorPct: event.target.value }); clearError('doctor_pct') }} />
            )}
          </Field>
        </div>
        <h3 className="recipe__heading">Позиции</h3>
        <ul className="recipe__rows">
          {values.rows.map((row, index) => {
            const item = catalog.find((candidate) => candidate.id === row.itemId)
            return (
              <li key={row.key} className="recipe__row" data-testid="price-recipe-item">
                <div className="recipe__item" data-error-key={errorKey('item_id', index)} tabIndex={-1}>
                  <StockItemField
                    label="Позиция"
                    items={catalog}
                    loading={stockLoading && catalog.length === 0}
                    loadError={stockError && catalog.length === 0}
                    onRetry={onRetryStock}
                    value={row.itemId}
                    onChange={(itemId) => patchRow(row.key, { itemId }, 'item_id', index)}
                    error={errors[errorKey('item_id', index)]}
                    disabled={busy}
                    testId="price-recipe-field-item"
                    errorTestId="price-recipe-field-item-error"
                  />
                </div>
                <div className="recipe__group" data-error-key={errorKey('group', index)}>
                  <span className="fld__label">Группа</span>
                  {phone ? (
                    <select className="input" aria-label="Группа" value={row.group} disabled={busy} data-testid="price-recipe-field-group"
                      onChange={(event) => patchRow(row.key, { group: event.target.value as RecipeGroup }, 'group', index)}>
                      {GROUP_OPTIONS.map((option) => (
                        <option key={option.id} value={option.id}>{option.label}</option>
                      ))}
                    </select>
                  ) : (
                    <Segmented label="Группа" options={GROUP_OPTIONS} value={row.group} disabled={busy} onChange={(group) => patchRow(row.key, { group }, 'group', index)} />
                  )}
                </div>
                <Field label="Количество" error={errors[errorKey('qty', index)]} errorTestId="price-recipe-field-qty-error">
                  {(control: FieldControlProps) => (
                    <div className="amount">
                      <input {...control} className="input" inputMode="decimal" autoComplete="off" value={row.qty} disabled={busy} data-error-key={errorKey('qty', index)} data-testid="price-recipe-field-qty"
                        onChange={(event) => patchRow(row.key, { qty: event.target.value }, 'qty', index)} />
                      <span className="amount__unit">{item?.unit ?? ''}</span>
                    </div>
                  )}
                </Field>
                <button type="button" className="btn btn--text recipe__remove" disabled={busy} aria-label={`Убрать: ${item?.name ?? 'позицию'}`} data-testid="price-recipe-item-remove" onClick={() => removeRow(row.key)}>
                  Убрать
                </button>
              </li>
            )
          })}
        </ul>
        <button type="button" className="btn" disabled={busy || values.rows.length >= MAX_RECIPE_ITEMS} data-testid="price-recipe-item-add" onClick={addRow}>
          + Добавить позицию
        </button>
        <p className="fld__hint recipe__note">Берём средний расход на одну услугу. Вес животного не учитывается.</p>
        {general && <InlineAlert testId="price-recipe-error">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}
