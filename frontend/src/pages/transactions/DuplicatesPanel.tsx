import type { RefObject } from 'react'
import { isApiError } from '../../api/errors'
import { useResolveDuplicate } from '../../api/mutations'
import { useTransactionList } from '../../api/queries'
import type { Transaction } from '../../api/types'
import { Pill } from '../../components/Pill'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { formatDayMonth } from '../../lib/dates'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { TxListSkeleton } from './TxList'
import { SOURCE_PILL, AmountCell, CategoryCell, DateCell, DescriptionText, SourcePill } from './txParts'
import { ALL_MONTHS_NOTE } from './TxPanel'

const NOTE =
  'Похоже, одна и та же операция попала к нам дважды, например из банка и из Ветменеджера. Выберите, какую оставить.'

interface DuplicatesPanelProps {
  referenceYear: number | undefined
  narrow: boolean
  headingRef: RefObject<HTMLHeadingElement | null>
}

function DupRow({
  tx,
  label,
  referenceYear,
  keepable,
  busy,
  onKeep,
}: {
  tx: Transaction
  label: string
  referenceYear: number | undefined
  keepable: boolean
  busy: boolean
  onKeep: () => void
}) {
  return (
    <div className="dup-row" data-testid="tx-row">
      <p className="dup-row__label">{label}</p>
      <div className="dup-row__main">
        <span className="dup-row__date">
          <DateCell date={tx.date} referenceYear={referenceYear} />
        </span>
        <span className="dup-row__op">
          <DescriptionText tx={tx} />
          <span className="tx-meta">{tx.account.name}</span>
        </span>
        <span className="dup-row__cat">
          <CategoryCell tx={tx} mode="all" disabled onEdit={() => undefined} />
        </span>
        <SourcePill source={tx.source} />
        <AmountCell tx={tx} />
      </div>
      {keepable && (
        <div className="dup-row__act">
          <button
            type="button"
            className="btn btn--sm"
            data-testid="keep-this"
            disabled={busy}
            aria-busy={busy || undefined}
            aria-label={`Оставить эту операцию: «${tx.description}», ${formatDayMonth(tx.date)}`}
            onClick={onKeep}
          >
            {busy ? 'Сохраняем…' : 'Оставить эту'}
          </button>
        </div>
      )}
    </div>
  )
}

export function DuplicatesPanel({ referenceYear, narrow, headingRef }: DuplicatesPanelProps) {
  const list = useTransactionList('duplicates', '')
  const resolve = useResolveDuplicate()
  const toast = useToast()
  const loading = list.isPending
  const slow = useSlowLoading(loading)
  const rows = (list.data?.pages ?? []).flatMap((page) => page.items)
  const busyId = resolve.isPending ? resolve.variables.id : null

  const fail = () => toast.show({ kind: 'error', message: 'Не получилось выполнить действие. Попробуйте ещё раз.' })

  const keep = (flagged: Transaction, kept: Transaction) => {
    resolve.mutate(
      { id: flagged.id, decision: { keepId: kept.id } },
      {
        onSuccess: () =>
          toast.show({
            message: `Оставили операцию от ${formatDayMonth(kept.date)} (${SOURCE_PILL[kept.source].text}). Вторая не учитывается.`,
          }),
        onError: fail,
      },
    )
  }

  const keepBoth = (flagged: Transaction) => {
    resolve.mutate(
      { id: flagged.id, decision: { keepBoth: true } },
      { onSuccess: () => toast.show({ message: 'Обе операции остались в учёте.' }), onError: fail },
    )
  }

  let body
  if (list.isError && rows.length === 0) {
    body = (
      <LoadErrorCard
        title="Не получилось загрузить операции"
        network={isApiError(list.error) && list.error.kind === 'network'}
        retrying={list.isFetching}
        onRetry={() => void list.refetch()}
      />
    )
  } else if (loading) {
    body = <TxListSkeleton narrow={narrow} />
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        icon="✅"
        title="Дублей нет"
        text="Если одна и та же операция придёт дважды, например из банка и из Ветменеджера, мы покажем её здесь."
      />
    )
  } else {
    body = (
      <div className="tx-panel">
        <p className="tx-note">{NOTE}</p>
        <ul className="dup-list">
          {rows.map((flagged) => {
            const pending = flagged.duplicate_state !== 'confirmed'
            const busy = busyId === flagged.id
            return (
              <li key={flagged.id} className="dup-pair" data-testid="dup-pair">
                <p className="dup-pair__reason">
                  Похоже на дубль{flagged.duplicate_reason ? ` · ${flagged.duplicate_reason}` : ''}
                  {!pending && (
                    <>
                      {' '}
                      <Pill variant="neutral">решено</Pill>
                    </>
                  )}
                </p>
                {flagged.duplicate_of && (
                  <DupRow
                    tx={flagged.duplicate_of}
                    label="Уже была в учёте"
                    referenceYear={referenceYear}
                    keepable={pending}
                    busy={busy}
                    onKeep={() => keep(flagged, flagged.duplicate_of as Transaction)}
                  />
                )}
                <DupRow
                  tx={flagged}
                  label="Пришла повторно"
                  referenceYear={referenceYear}
                  keepable={pending}
                  busy={busy}
                  onKeep={() => keep(flagged, flagged)}
                />
                {pending && (
                  <div className="dup-pair__foot">
                    <p className="tx-meta">
                      Вторая операция перестанет учитываться в остатке и отчётах. В истории она останется с пометкой «дубль».
                    </p>
                    <button type="button" className="btn btn--text" disabled={busy} onClick={() => keepBoth(flagged)}>
                      Это не дубль, оставить обе
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
        {list.hasNextPage && (
          <div className="tx-more">
            <button type="button" className="btn btn--text" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
              {list.isFetchingNextPage ? 'Загружаем…' : 'Показать ещё'}
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div data-testid="tx-list" aria-busy={loading}>
      <h2 className="sr-only" tabIndex={-1} ref={headingRef}>
        Возможные дубли
      </h2>
      <p className="tx-scope">{ALL_MONTHS_NOTE}</p>
      {loading && <p className="sr-only" role="status">Загружаем операции</p>}
      {body}
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
    </div>
  )
}
