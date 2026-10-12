import type { Transaction } from '../../api/types'
import { DateCell, DescriptionText, DuplicateMark, AmountCell, CategoryCell, MetaLine, SourcePill } from './txParts'

export interface TxListProps {
  rows: Transaction[]
  /** "all": Все; "check": На проверку (action column, account moves under the description). */
  mode: 'all' | 'check'
  narrow: boolean
  referenceYear: number | undefined
  caption: string
  busyId: string | null
  onEdit: (tx: Transaction) => void
  onConfirm: (tx: Transaction) => void
}

interface ActionsProps {
  tx: Transaction
  busy: boolean
  block: boolean
  onEdit: (tx: Transaction) => void
  onConfirm: (tx: Transaction) => void
}

/** Buttons of the "На проверку" tab: confirm the suggestion or choose the category. */
function CheckActions({ tx, busy, block, onEdit, onConfirm }: ActionsProps) {
  const className = block ? 'tx-actions tx-actions--block' : 'tx-actions'
  const suggestion = tx.suggestion
  return (
    <div className={className}>
      {suggestion && (
        <button
          type="button"
          className="btn btn--sm btn--primary"
          data-testid="tx-confirm"
          disabled={busy}
          aria-busy={busy || undefined}
          aria-label={`Подтвердить статью «${suggestion.category.name}» для операции «${tx.description}»`}
          onClick={() => onConfirm(tx)}
        >
          {busy ? 'Сохраняем…' : `Подтвердить: ${suggestion.category.name}`}
        </button>
      )}
      <button
        type="button"
        className="btn btn--sm"
        data-testid="tx-category"
        disabled={busy}
        aria-label={`${suggestion ? 'Другая статья' : 'Выбрать статью'} для операции «${tx.description}»`}
        onClick={() => onEdit(tx)}
      >
        {suggestion ? 'Другая статья' : 'Выбрать статью'}
      </button>
    </div>
  )
}

function SuggestionLine({ tx }: { tx: Transaction }) {
  if (!tx.suggestion) return null
  return (
    <span className="tx-suggest">
      Предлагаем «{tx.suggestion.category.name}»: {tx.suggestion.text}
    </span>
  )
}

function TableRow(props: Omit<TxListProps, 'rows' | 'narrow' | 'caption'> & { tx: Transaction }) {
  const { tx, mode, referenceYear, busyId, onEdit, onConfirm } = props
  const muted = tx.status === 'duplicate'
  const check = mode === 'check'
  return (
    <tr className={muted ? 'tx-row tx-row--muted' : 'tx-row'} data-testid="tx-row">
      <td className="tx-col-date">
        <DateCell date={tx.date} referenceYear={referenceYear} />
      </td>
      <td className="tx-col-op">
        <div className="tx-op">
          <DescriptionText tx={tx} />
          <DuplicateMark tx={tx} />
        </div>
        {check && <MetaLine tx={tx} />}
        {check && <SuggestionLine tx={tx} />}
      </td>
      <td className="tx-col-cat">
        <CategoryCell tx={tx} mode={mode} onEdit={onEdit} />
      </td>
      {!check && <td className="tx-col-acc">{tx.account.name}</td>}
      {!check && (
        <td className="tx-col-src">
          <SourcePill source={tx.source} />
        </td>
      )}
      <td className="tx-col-sum">
        <AmountCell tx={tx} />
      </td>
      {check && (
        <td className="tx-col-act">
          <CheckActions tx={tx} busy={busyId === tx.id} block={false} onEdit={onEdit} onConfirm={onConfirm} />
        </td>
      )}
    </tr>
  )
}

function CardRow(props: Omit<TxListProps, 'rows' | 'narrow' | 'caption'> & { tx: Transaction }) {
  const { tx, mode, referenceYear, busyId, onEdit, onConfirm } = props
  const muted = tx.status === 'duplicate'
  const check = mode === 'check'
  return (
    <li className={muted ? 'tx-card tx-row--muted' : 'tx-card'} data-testid="tx-row">
      <div className="tx-card__top">
        <div className="tx-card__op">
          <DescriptionText tx={tx} />
        </div>
        <AmountCell tx={tx} />
      </div>
      <div className="tx-card__meta">
        <DateCell date={tx.date} referenceYear={referenceYear} />
        <span aria-hidden="true">·</span>
        <span>{tx.account.name}</span>
        <SourcePill source={tx.source} />
        <DuplicateMark tx={tx} />
      </div>
      {check && <SuggestionLine tx={tx} />}
      <div className="tx-card__cat">
        <CategoryCell tx={tx} mode={mode} onEdit={onEdit} />
      </div>
      {check && <CheckActions tx={tx} busy={busyId === tx.id} block onEdit={onEdit} onConfirm={onConfirm} />}
    </li>
  )
}

/** Table above 1100px, cards below: two separate markups, the table is not turned into blocks by CSS. */
export function TxList({ rows, mode, narrow, referenceYear, caption, busyId, onEdit, onConfirm }: TxListProps) {
  const shared = { mode, referenceYear, busyId, onEdit, onConfirm }
  if (narrow) {
    return (
      <ul className="tx-cards" aria-label={caption}>
        {rows.map((tx) => (
          <CardRow key={tx.id} tx={tx} {...shared} />
        ))}
      </ul>
    )
  }
  const check = mode === 'check'
  return (
    <table className={check ? 'tx-table tx-table--check' : 'tx-table'}>
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Дата</th>
          <th scope="col">Операция</th>
          <th scope="col">Статья</th>
          {!check && <th scope="col">Счёт</th>}
          {!check && <th scope="col">Источник</th>}
          <th scope="col" className="tx-th-sum">
            Сумма
          </th>
          {check && (
            <th scope="col">
              <span className="sr-only">Действие</span>
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {rows.map((tx) => (
          <TableRow key={tx.id} tx={tx} {...shared} />
        ))}
      </tbody>
    </table>
  )
}

export function TxListSkeleton({ narrow }: { narrow: boolean }) {
  return (
    <div className={narrow ? 'tx-skel tx-skel--narrow' : 'tx-skel'} aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="tx-skel__row">
          <span className="tx-skel__bar tx-skel__bar--date" />
          <span className="tx-skel__bar tx-skel__bar--op" />
          <span className="tx-skel__bar tx-skel__bar--sum" />
        </div>
      ))}
    </div>
  )
}
