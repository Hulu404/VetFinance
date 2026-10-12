import { useQuery } from '@tanstack/react-query'
import { useId, useRef, useState } from 'react'
import { isApiError } from '../../api/errors'
import { fetchRulePreview, useUpdateCategory } from '../../api/mutations'
import { useCategories } from '../../api/queries'
import type { RulePreview, Transaction, TransactionUpdateResult } from '../../api/types'
import { CategoryField } from '../../components/CategoryField'
import { Dialog } from '../../components/Dialog'
import { CheckField } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { formatDayMonth } from '../../lib/dates'
import { pluralRu } from '../../lib/format'
import { SOURCE_PILL, signedMoney } from './txParts'

interface CategoryDialogProps {
  tx: Transaction
  onClose: () => void
  onSaved: (result: TransactionUpdateResult, categoryName: string) => void
  onRefresh: () => void
  fallbackFocus: () => void
}

function loadedOperations(count: number): string {
  return count % 10 === 1 && count % 100 !== 11 ? 'уже загруженной операции' : 'уже загруженным операциям'
}

interface RuleLineProps {
  categoryName: string | null
  createRule: boolean
  loading: boolean
  failed: boolean
  preview: RulePreview | undefined
}

/** The line under the checkbox; its text depends on the state of the preview (design/screens/transactions.md). */
export function ruleLine({ categoryName, createRule, loading, failed, preview }: RuleLineProps): string | null {
  if (!categoryName) return 'Выберите статью, и мы покажем, к скольким операциям применится правило.'
  if (loading) return null
  if (failed) return 'Не получилось посчитать, к скольким операциям применится правило. Оно всё равно создастся.'
  if (!preview) return null
  if (preview.already_exists) {
    return 'Такое правило уже есть, оно применилось бы к этой операции автоматически. Проверьте вкладку «Правила разнесения».'
  }
  if (!preview.can_create) return 'Для этой операции правило не создать: у платежа не определён контрагент.'
  if (!createRule) return 'Изменится только эта операция.'
  const head = `Правило: если контрагент «${preview.match_text ?? ''}», статья «${categoryName}».`
  if (preview.matches_count > 0) {
    return `${head} Применится к ${preview.matches_count} ${loadedOperations(preview.matches_count)} без статьи и ко всем новым.`
  }
  return `${head} Сейчас других таких операций без статьи нет, правило сработает на новых.`
}

export function CategoryDialog({ tx, onClose, onSaved, onRefresh, fallbackFocus }: CategoryDialogProps) {
  const categories = useCategories()
  const update = useUpdateCategory()
  const initial = tx.category?.id ?? null
  const [categoryId, setCategoryId] = useState<string | null>(initial)
  const [createRule, setCreateRule] = useState(true)
  const [categoryError, setCategoryError] = useState<string | null>(null)
  const closeRef = useRef<(() => void) | null>(null)
  const lineId = useId()

  const preview = useQuery({
    queryKey: ['rule-preview', tx.id, categoryId],
    queryFn: ({ signal }) => fetchRulePreview(tx.id, categoryId ?? '', signal),
    enabled: categoryId !== null,
    staleTime: 0,
    retry: false,
  })

  const items = categories.data?.items ?? []
  const chosen = items.find((item) => item.id === categoryId) ?? null
  const ruleBlocked = preview.data ? !preview.data.can_create || preview.data.already_exists : false
  const effectiveRule = createRule && !ruleBlocked
  const line = ruleLine({
    categoryName: chosen?.name ?? null,
    createRule: effectiveRule,
    loading: categoryId !== null && preview.isPending,
    failed: preview.isError,
    preview: preview.data,
  })
  const dirty = categoryId !== initial || !createRule

  const submit = () => {
    if (!chosen) {
      setCategoryError('Выберите статью')
      return
    }
    update.mutate(
      { id: tx.id, categoryId: chosen.id, createRule: effectiveRule },
      { onSuccess: (result) => onSaved(result, chosen.name) },
    )
  }

  const error = update.error
  const conflict = isApiError(error) && error.kind === 'conflict'

  return (
    <Dialog
      title="Статья для операции"
      onClose={onClose}
      dirty={dirty}
      busy={update.isPending}
      fallbackFocus={fallbackFocus}
      closeRef={closeRef}
      testId="category-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={update.isPending} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn--primary"
            data-testid="category-save"
            disabled={update.isPending}
            aria-busy={update.isPending || undefined}
            onClick={submit}
          >
            {update.isPending ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </>
      }
    >
      <div className="opsum">
        <div className="opsum__text">
          <p className="opsum__title">{tx.description}</p>
          <p className="opsum__meta">
            {formatDayMonth(tx.date)} · {tx.account.name} · {SOURCE_PILL[tx.source].text}
          </p>
        </div>
        <p className="opsum__sum">{signedMoney(tx.amount)}</p>
      </div>
      <CategoryField
        label="Статья"
        categories={items}
        loading={categories.isPending}
        loadError={categories.isError}
        onRetry={() => void categories.refetch()}
        kind={tx.kind === 'in' ? 'in' : 'out'}
        value={categoryId}
        onChange={(id) => {
          setCategoryId(id)
          setCategoryError(null)
        }}
        error={categoryError}
        disabled={update.isPending}
        defaultOpen
        testId="category-picker"
      />
      <CheckField
        label="Создать правило для похожих операций"
        checked={effectiveRule}
        onChange={setCreateRule}
        disabled={ruleBlocked || update.isPending}
        testId="create-rule"
        describedBy={lineId}
      />
      <p id={lineId} className="rule-line" aria-live="polite">
        {categoryId !== null && preview.isPending ? <span className="rule-line__skeleton" aria-hidden="true" /> : line}
      </p>
      {update.isError && (
        <InlineAlert testId="category-error">
          {conflict ? (
            <>
              Эта операция уже изменилась. Обновите список и повторите.
              <button type="button" className="btn btn--text" onClick={onRefresh}>
                Обновить список
              </button>
            </>
          ) : (
            'Не получилось сохранить статью. Операция осталась как была. Попробуйте ещё раз.'
          )}
        </InlineAlert>
      )}
    </Dialog>
  )
}

/** Toast text after the category was saved (design/screens/transactions.md, "После сохранения"). */
export function savedMessage(result: TransactionUpdateResult, categoryName: string): { message: string; rule: boolean } {
  const rule = result.rule
  if (!rule) return { message: `Статья «${categoryName}» сохранена.`, rule: false }
  if (rule.applied_count > 0) {
    const noun = pluralRu(rule.applied_count, 'операции', 'операциям', 'операциям')
    return {
      message: `Статья «${categoryName}» сохранена. Правило создано и применилось ещё к ${rule.applied_count} ${noun}.`,
      rule: true,
    }
  }
  return {
    message: `Статья «${categoryName}» сохранена. Правило создано: новые такие операции будут разноситься сами.`,
    rule: true,
  }
}
