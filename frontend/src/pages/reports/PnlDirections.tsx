import type { Figure, PnlReport, PnlRow } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { formatExpense, formatFigure, formatMoney } from '../../lib/format'

/** Below this width the six columns become cards (design/screens/pnl.md, "Раскладка"). */
const CARDS_QUERY = '(max-width: 720px)'

type DirectionKey = 'services' | 'goods' | 'common' | 'total'
type CellKey = 'revenue' | 'share' | 'costs' | 'margin' | 'margin-pct'

interface Cell {
  key: CellKey
  /** Column title and card caption. */
  title: string
  figure: Figure | null
  /** Text as shown; expenses carry the minus here. */
  text: string
  /** Path of the API field for `data-figure`. */
  path: string
}

interface DirectionRow {
  key: DirectionKey
  label: string
  hint?: string
  cells: Cell[]
}

const COLUMNS: Array<{ key: CellKey; title: string }> = [
  { key: 'revenue', title: 'Выручка' },
  { key: 'share', title: 'Доля' },
  { key: 'costs', title: 'Прямые расходы' },
  { key: 'margin', title: 'Маржа' },
  { key: 'margin-pct', title: 'Маржа, %' },
]

function money(figure: Figure): string {
  return formatMoney(figure.value)
}

function expense(figure: Figure): string {
  return formatExpense(figure.value)
}

function cell(key: CellKey, figure: Figure | null, path: string, text?: string): Cell {
  const title = COLUMNS.find((column) => column.key === key)?.title ?? ''
  return { key, title, figure, path, text: figure ? (text ?? formatFigure(figure)) : '—' }
}

function rowOf(report: PnlReport, key: string): PnlRow | undefined {
  return report.rows.find((row) => row.key === key)
}

/** Picks the figures the API gave for every row; nothing is added up here. */
function buildRows(report: PnlReport): DirectionRow[] {
  const directions = report.directions ?? []
  const rows: DirectionRow[] = directions.map((direction) => ({
    key: direction.direction,
    label: direction.label,
    cells: [
      cell('revenue', direction.revenue, `directions.${direction.direction}.revenue`, money(direction.revenue)),
      cell('share', direction.revenue_share_pct, `directions.${direction.direction}.revenue_share_pct`),
      cell('costs', direction.direct_costs, `directions.${direction.direction}.direct_costs`, expense(direction.direct_costs)),
      cell('margin', direction.margin, `directions.${direction.direction}.margin`, money(direction.margin)),
      cell('margin-pct', direction.margin_pct, `directions.${direction.direction}.margin_pct`),
    ],
  }))
  const common = report.common_variable
  if (common) {
    rows.push({
      key: 'common',
      label: 'Общие переменные расходы',
      hint: 'не относятся ни к услугам, ни к товарам',
      cells: [
        cell('revenue', null, ''),
        cell('share', null, ''),
        cell('costs', common, 'common_variable', expense(common)),
        cell('margin', common, 'common_variable', expense(common)),
        cell('margin-pct', null, ''),
      ],
    })
  }
  const revenue = rowOf(report, 'revenue')
  const variable = rowOf(report, 'variable')
  const marginal = rowOf(report, 'marginal_profit')
  if (revenue && variable && marginal) {
    rows.push({
      key: 'total',
      label: 'Маржинальная прибыль',
      cells: [
        cell('revenue', revenue.amount, 'rows.revenue.amount', money(revenue.amount)),
        cell('share', revenue.share_pct ?? null, 'rows.revenue.share_pct'),
        cell('costs', variable.amount, 'rows.variable.amount', expense(variable.amount)),
        cell('margin', marginal.amount, 'rows.marginal_profit.amount', money(marginal.amount)),
        cell('margin-pct', marginal.share_pct ?? null, 'rows.marginal_profit.share_pct'),
      ],
    })
  }
  return rows
}

function CellValue({ cellData, rowLabel }: { cellData: Cell; rowLabel: string }) {
  if (!cellData.figure) return <>—</>
  return (
    <span data-testid={`pnl-direction-${cellData.key}`} data-figure={cellData.path}>
      <FigureButton
        figure={cellData.figure}
        title={`${rowLabel} · ${cellData.title.toLowerCase()}`}
        spokenValue={`${rowLabel}, ${cellData.title.toLowerCase()}: ${cellData.text}`}
      >
        {cellData.text}
      </FigureButton>
    </span>
  )
}

function TableView({ rows }: { rows: DirectionRow[] }) {
  return (
    <div className="dir">
      <table className="dir__table">
        <caption className="sr-only">Выручка и маржа по направлениям</caption>
        <thead>
          <tr>
            <th scope="col">Направление</th>
            {COLUMNS.map((column) => (
              <th key={column.key} scope="col" className="dir__num">
                {column.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className={`dir__row dir__row--${row.key}`} data-testid="pnl-direction" data-key={row.key}>
              <th scope="row">
                {row.label}
                {row.hint && <span className="dir__hint">{row.hint}</span>}
              </th>
              {row.cells.map((item) => (
                <td key={item.key} className="dir__num">
                  <CellValue cellData={item} rowLabel={row.label} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CardsView({ rows }: { rows: DirectionRow[] }) {
  return (
    <ul className="dir dir--cards">
      {rows.map((row) => (
        <li key={row.key} className={`dir__card dir__row--${row.key}`} data-testid="pnl-direction" data-key={row.key}>
          <h3 className="dir__card-title">{row.label}</h3>
          {row.hint && <p className="dir__hint">{row.hint}</p>}
          <dl className="dir__pairs">
            {row.cells.map((item) => (
              <div key={item.key} className="dir__pair">
                <dt>{item.title}</dt>
                <dd>
                  <CellValue cellData={item} rowLabel={row.label} />
                </dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ul>
  )
}

/** "Услуги и товары": revenue and margin of the two directions, the common variable costs and the total (function 18). */
export function PnlDirections({ report }: { report: PnlReport }) {
  const cards = useMediaQuery(CARDS_QUERY)
  const rows = buildRows(report)
  return cards ? <CardsView rows={rows} /> : <TableView rows={rows} />
}
