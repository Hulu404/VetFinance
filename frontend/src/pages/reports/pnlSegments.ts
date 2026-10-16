import type { PnlDirection, PnlRow } from '../../api/types'
import type { StructureSegment } from '../../components/StructureBar'
import { formatFigure } from '../../lib/format'

/** The legend says "ФОТ", the table row "ФОТ (оклады)". */
const SHORT_LABELS: Record<string, string> = { fixed_payroll: 'ФОТ' }

function find(rows: PnlRow[], key: string): PnlRow | undefined {
  return rows.find((row) => row.key === key)
}

function segmentOf(row: PnlRow, color: number): StructureSegment {
  return {
    key: row.key,
    label: SHORT_LABELS[row.key] ?? row.label,
    share: row.share_pct ?? null,
    tip: row.amount,
    figureKey: `rows.${row.key}.share_pct`,
    color,
  }
}

/**
 * Where the revenue goes: variable, payroll, other fixed, taxes, obligations, net profit.
 * Without the split of the fixed expenses the parent row stands alone. A loss leaves out the profit segment.
 * Rows are only picked here, the shares come from the API as they are.
 */
export function buildRevenueSegments(rows: PnlRow[]): StructureSegment[] {
  const fixed = find(rows, 'fixed')
  const parts: PnlRow[] = []
  const variable = find(rows, 'variable')
  if (variable) parts.push(variable)
  const children = fixed?.children ?? []
  if (children.length > 0) parts.push(...children)
  else if (fixed) parts.push(fixed)
  for (const key of ['taxes', 'obligations']) {
    const row = find(rows, key)
    if (row) parts.push(row)
  }
  const net = find(rows, 'net_profit')
  if (net && net.amount.value >= 0) parts.push(net)
  return parts.map((row, index) => segmentOf(row, index + 1))
}

export function hasAnyShare(segments: StructureSegment[]): boolean {
  return segments.some((segment) => segment.share !== null)
}

/** Services and goods as two parts of the revenue (mode "Услуги и товары"). */
export function buildDirectionSegments(directions: PnlDirection[]): StructureSegment[] {
  return directions.map((direction, index) => ({
    key: direction.direction,
    label: direction.label,
    share: direction.revenue_share_pct,
    tip: direction.revenue,
    figureKey: `directions.${direction.direction}.revenue_share_pct`,
    color: index === 0 ? 1 : 3,
  }))
}

/** "Структура выручки: переменные расходы 51,0%, ФОТ 11,0%, …" for a screen reader. */
export function structureAriaLabel(prefix: string, segments: StructureSegment[]): string {
  const parts = segments.map((segment) => `${segment.label.toLowerCase()} ${segment.share ? formatFigure(segment.share) : '—'}`)
  return `${prefix}: ${parts.join(', ')}`
}
