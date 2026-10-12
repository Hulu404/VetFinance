import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useTransactionCounts, useTransactionList } from '../../api/queries'
import type { Transaction } from '../../api/types'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { formatMonthTitle, monthNameLower } from '../../lib/dates'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { TxList, TxListSkeleton } from './TxList'

const CHECK_NOTE =
  'Эти операции не удалось отнести к статье автоматически. Выберите статью: похожие дальше будут разноситься сами.'
export const ALL_MONTHS_NOTE = 'Показаны операции за все месяцы.'

interface TxPanelProps {
  tab: 'all' | 'check'
  month: string | null
  referenceYear: number | undefined
  narrow: boolean
  busyId: string | null
  headingRef: RefObject<HTMLHeadingElement | null>
  onEdit: (tx: Transaction) => void
  onConfirm: (tx: Transaction) => void
  onOpenImport: () => void
  onOpenManual: () => void
}

function EmptyAll({ month, none, onOpenImport, onOpenManual }: { month: string; none: boolean } & Pick<TxPanelProps, 'onOpenImport' | 'onOpenManual'>) {
  if (none) {
    return (
      <EmptyState
        testId="tx-empty"
        icon="🧾"
        title="Операций пока нет"
        text="Загрузите выписку из банка или добавьте операцию вручную. Операции из Ветменеджера придут после подключения."
        actions={
          <>
            <button type="button" className="btn btn--primary" onClick={onOpenImport}>
              Загрузить выписку
            </button>
            <button type="button" className="btn" onClick={onOpenManual}>
              + Операция
            </button>
            <Link className="btn btn--text" to="/settings/connections/vetmanager">
              Подключить Ветменеджер
            </Link>
          </>
        }
      />
    )
  }
  return (
    <EmptyState
      testId="tx-empty"
      icon="🧾"
      title={`За ${monthNameLower(month)} ${month.slice(0, 4)} операций нет`}
      text="Выберите другой месяц или загрузите выписку."
      actions={
        <button type="button" className="btn" onClick={onOpenImport}>
          Загрузить выписку
        </button>
      }
    />
  )
}

export function TxPanel(props: TxPanelProps) {
  const { tab, month, referenceYear, narrow, busyId, headingRef, onEdit, onConfirm, onOpenImport, onOpenManual } = props
  const list = useTransactionList(tab, month ?? '')
  const counts = useTransactionCounts()
  const loading = list.isPending
  const slow = useSlowLoading(loading)
  const rows = (list.data?.pages ?? []).flatMap((page) => page.items)

  const caption = tab === 'all' && month ? `Операции за ${formatMonthTitle(month)}` : 'Операции, которым нужна статья'
  const note = tab === 'check' ? CHECK_NOTE : null

  let body
  if (tab === 'all' && !month) {
    body = <TxListSkeleton narrow={narrow} />
  } else if (list.isError && rows.length === 0) {
    body = (
      <LoadErrorCard
        testId="tx-error"
        title="Не получилось загрузить операции"
        network={isApiError(list.error) && list.error.kind === 'network'}
        retrying={list.isFetching}
        onRetry={() => void list.refetch()}
      />
    )
  } else if (loading) {
    body = <TxListSkeleton narrow={narrow} />
  } else if (rows.length === 0) {
    body =
      tab === 'check' ? (
        <EmptyState testId="tx-empty" icon="✅" title="Всё разнесено" text="Операций без статьи нет. Если появятся, они будут здесь." />
      ) : (
        <EmptyAll month={month ?? ''} none={counts.data?.all === 0} onOpenImport={onOpenImport} onOpenManual={onOpenManual} />
      )
  } else {
    body = (
      <div className="tx-panel">
        {note && <p className="tx-note">{note}</p>}
        <TxList
          rows={rows}
          mode={tab}
          narrow={narrow}
          referenceYear={referenceYear}
          caption={caption}
          busyId={busyId}
          onEdit={onEdit}
          onConfirm={onConfirm}
        />
        {list.isFetchNextPageError && (
          <p className="tx-more-error" role="alert">
            Не получилось загрузить ещё{' '}
            <button type="button" className="btn btn--text" onClick={() => void list.fetchNextPage()}>
              Повторить
            </button>
          </p>
        )}
        {list.hasNextPage && !list.isFetchNextPageError && (
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
        {caption}
      </h2>
      {tab === 'check' && <p className="tx-scope">{ALL_MONTHS_NOTE}</p>}
      {loading && <p className="sr-only" role="status">Загружаем операции</p>}
      {body}
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
    </div>
  )
}
