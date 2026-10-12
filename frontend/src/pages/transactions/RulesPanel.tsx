import { useEffect, useRef, useState, type RefObject } from 'react'
import { isApiError } from '../../api/errors'
import { useDeleteRule } from '../../api/mutations'
import { useCategoryRules } from '../../api/queries'
import type { CategoryRule } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { FigureButton } from '../../components/FigureButton'
import { Pill } from '../../components/Pill'
import { EmptyState, InlineAlert, LoadErrorCard } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { TxListSkeleton } from './TxList'

const NOTE =
  'Правила создаются сами, когда вы выбираете статью и оставляете галочку «Создать правило». Один раз поправили, дальше разносится автоматически.'
const HIGHLIGHT_MS = 3000

interface RulesPanelProps {
  narrow: boolean
  highlightId: string | null
  headingRef: RefObject<HTMLHeadingElement | null>
}

/** "Если контрагент «ИП Волков»" for a rule by the counterparty, "Если в назначении «…»" for a rule by text. */
function ruleCondition(rule: CategoryRule): string {
  return rule.match === 'text' ? `Если в назначении «${rule.match_text}»` : `Если контрагент «${rule.match_text}»`
}

function directionNote(rule: CategoryRule): string | null {
  if (rule.direction === 'out') return 'только расходы'
  if (rule.direction === 'in') return 'только поступления'
  return null
}

function DeleteRuleDialog({ rule, onClose }: { rule: CategoryRule; onClose: () => void }) {
  const remove = useDeleteRule()
  const toast = useToast()
  const [failed, setFailed] = useState(false)
  const closeRef = useRef<(() => void) | null>(null)

  const submit = () => {
    setFailed(false)
    remove.mutate(rule.id, {
      onSuccess: () => {
        toast.show({ message: 'Правило удалено.' })
        onClose()
      },
      onError: () => setFailed(true),
    })
  }

  return (
    <Dialog
      title="Удалить правило?"
      subtitle={`Уже разнесённые операции останутся в своих статьях. Новые операции с «${rule.match_text}» будут попадать на проверку.`}
      alert
      busy={remove.isPending}
      onClose={onClose}
      closeRef={closeRef}
      testId="rule-delete-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={remove.isPending} onClick={() => closeRef.current?.()}>
            Не удалять
          </button>
          <button type="button" className="btn btn--danger" disabled={remove.isPending} onClick={submit} data-testid="rule-delete-confirm">
            {remove.isPending ? 'Удаляем…' : 'Удалить правило'}
          </button>
        </>
      }
    >
      {failed ? <InlineAlert>Не получилось удалить правило. Попробуйте ещё раз.</InlineAlert> : null}
    </Dialog>
  )
}

export function RulesPanel({ narrow, highlightId, headingRef }: RulesPanelProps) {
  const rules = useCategoryRules()
  const [target, setTarget] = useState<CategoryRule | null>(null)
  const [lit, setLit] = useState<string | null>(highlightId)

  useEffect(() => {
    setLit(highlightId)
    if (!highlightId) return
    const timer = window.setTimeout(() => setLit(null), HIGHLIGHT_MS)
    return () => window.clearTimeout(timer)
  }, [highlightId])

  const items = rules.data?.items ?? []
  let body
  if (rules.isError && !rules.data) {
    body = (
      <LoadErrorCard
        title="Не получилось загрузить правила"
        network={isApiError(rules.error) && rules.error.kind === 'network'}
        retrying={rules.isFetching}
        onRetry={() => void rules.refetch()}
      />
    )
  } else if (rules.isPending) {
    body = <TxListSkeleton narrow={narrow} />
  } else if (items.length === 0) {
    body = (
      <EmptyState
        icon="📏"
        title="Правил пока нет"
        text="Они появятся, когда вы выберете статью для операции и оставите галочку «Создать правило»."
      />
    )
  } else if (narrow) {
    body = (
      <div className="tx-panel">
        <p className="tx-note">{NOTE}</p>
        <ul className="tx-cards">
          {items.map((rule) => (
            <li key={rule.id} className={rule.id === lit ? 'tx-card-row tx-card-row--lit' : 'tx-card-row'} data-testid="rule-row">
              <p className="rule-text">{ruleCondition(rule)}</p>
              {directionNote(rule) && <p className="tx-meta">{directionNote(rule)}</p>}
              <div className="rule-meta">
                <Pill variant="neutral">{rule.category.name}</Pill>
                <span>
                  Сработало <FigureButton figure={rule.applied_count} title="Сработало" /> раз
                </span>
              </div>
              <button type="button" className="btn btn--block" onClick={() => setTarget(rule)} aria-label={`Удалить правило «${rule.match_text}»`}>
                Удалить
              </button>
            </li>
          ))}
        </ul>
      </div>
    )
  } else {
    body = (
      <div className="tx-panel">
        <p className="tx-note">{NOTE}</p>
        <table className="tx-table tx-table--rules">
          <caption className="sr-only">Правила разнесения</caption>
          <thead>
            <tr>
              <th scope="col">Если контрагент</th>
              <th scope="col">Статья</th>
              <th scope="col" className="tx-th-sum">
                Сработало
              </th>
              <th scope="col">
                <span className="sr-only">Действие</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((rule) => (
              <tr key={rule.id} className={rule.id === lit ? 'tx-row tx-row--lit' : 'tx-row'} data-testid="rule-row">
                <td className="rule-text">
                  {rule.match === 'text' ? `В назначении «${rule.match_text}»` : `«${rule.match_text}»`}
                  {directionNote(rule) && <span className="tx-meta">{directionNote(rule)}</span>}
                </td>
                <td>
                  <Pill variant="neutral">{rule.category.name}</Pill>
                </td>
                <td className="tx-col-sum">
                  <FigureButton figure={rule.applied_count} title="Сработало" />
                </td>
                <td className="tx-col-act">
                  <button type="button" className="btn btn--sm" onClick={() => setTarget(rule)} aria-label={`Удалить правило «${rule.match_text}»`}>
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div data-testid="tx-list" aria-busy={rules.isPending}>
      <h2 className="sr-only" tabIndex={-1} ref={headingRef}>
        Правила разнесения
      </h2>
      {body}
      {target && <DeleteRuleDialog rule={target} onClose={() => setTarget(null)} />}
    </div>
  )
}
