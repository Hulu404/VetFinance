/* The table gets `display: grid` on a phone, which drops the table semantics in some browsers: the roles put them back. */
import type { PnlRow } from '../api/types'
import { formatExpense, formatFigure, formatMoney } from '../lib/format'
import { FigureButton } from './FigureButton'
import { Pill } from './Pill'
import './ReportTable.css'

interface StatementTableProps {
  rows: PnlRow[]
  /** Hide the children of the fixed expenses (the bridge "от маржи до чистой прибыли" lists top rows only). */
  flat?: boolean
}

/** The amount as shown: an expense is stored positive and gets the minus here (design/components.md, section 18). */
function shownAmount(row: PnlRow): string {
  return row.kind === 'expense' || row.kind === 'child' ? formatExpense(row.amount.value) : formatMoney(row.amount.value)
}

function StatementRow({ row, child }: { row: PnlRow; child: boolean }) {
  const kind = child ? 'child' : row.kind
  const amountText = shownAmount(row)
  const share = row.share_pct ?? null
  const negativeTotal = kind === 'total' && row.amount.value < 0
  const tipValue = share ? `${amountText} · ${formatFigure(share)}` : amountText
  return (
    <tr
      role="row"
      className={`stmt__row stmt__row--${kind}${negativeTotal ? ' stmt__row--neg' : ''}`}
      data-testid="pnl-row"
      data-key={row.key}
      data-kind={kind}
    >
      <th scope="row" role="rowheader" className="stmt__name">
        <span className="stmt__bar">
          {row.label}
          {row.warning === 'no_obligations' && (
            <span className="stmt__warn" data-testid="pnl-row-warning">
              <Pill variant="warning">не заполнено</Pill>
            </span>
          )}
        </span>
      </th>
      <td className="stmt__amount">
        <span data-testid="pnl-row-amount" data-key={row.key} data-figure={`rows.${row.key}.amount`}>
          <FigureButton figure={row.amount} title={row.label} tipValue={tipValue} spokenValue={`${row.label}: ${amountText}`}>
            {amountText}
          </FigureButton>
        </span>
      </td>
      <td className="stmt__share">
        <span data-testid="pnl-row-share" data-key={row.key} data-figure={`rows.${row.key}.share_pct`}>
          {share ? (
            <FigureButton figure={share} title={`${row.label} · доля выручки`} spokenValue={`${row.label}, доля выручки ${formatFigure(share)}`}>
              {formatFigure(share)}
            </FigureButton>
          ) : (
            '—'
          )}
        </span>
      </td>
    </tr>
  )
}

/** The P&L statement: name, amount, share (variant "statement" of ReportTable). */
export function StatementTable({ rows, flat = false }: StatementTableProps) {
  return (
    <div className="stmt" data-testid="pnl-table">
      <table role="table" className="stmt__table">
        <caption className="sr-only">Прибыль и убытки</caption>
        <thead className="sr-only">
          <tr role="row">
            <th scope="col" role="columnheader">
              Статья
            </th>
            <th scope="col" role="columnheader">
              Сумма
            </th>
            <th scope="col" role="columnheader">
              Доля выручки
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <RowWithChildren key={row.key} row={row} flat={flat} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RowWithChildren({ row, flat }: { row: PnlRow; flat: boolean }) {
  return (
    <>
      <StatementRow row={row} child={false} />
      {!flat && (row.children ?? []).map((child) => <StatementRow key={child.key} row={child} child />)}
    </>
  )
}

const STATEMENT_SKELETON_ROWS = 9

/** Placeholders with the height of the finished table, so the page does not jump. */
export function StatementSkeleton({ rows = STATEMENT_SKELETON_ROWS }: { rows?: number }) {
  return (
    <div className="stmt stmt--loading" data-testid="pnl-loading" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="stmt__skeleton-row">
          <span className="skel skel--name" />
          <span className="skel skel--amount" />
          <span className="skel skel--share" />
        </div>
      ))}
    </div>
  )
}
