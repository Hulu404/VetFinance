import type { ReactNode } from 'react'
import type { Figure, PricePart, PricePartKey } from '../api/types'
import { formatFigure, formatPercent } from '../lib/format'
import { FigureButton } from './FigureButton'
import { Pill } from './Pill'
import './PriceBar.css'

export type PriceBarKey = PricePartKey | 'net'

export interface PriceBarEntry {
  key: PriceBarKey
  label: string
  /** Sum of the part as given by the API; null: the part is not filled. */
  amount: Figure | null
  /** Share of the price as given by the API. Its value sets the width of the segment (a picture, not a calculation). */
  share: Figure | null
  /** The sum is there but a warehouse item without a purchase price is not in it. */
  incomplete?: boolean
}

const COLOR_INDEX: Record<PriceBarKey, string> = {
  doctor_pay: 'doctor',
  drugs: 'drugs',
  anesthesia: 'anesthesia',
  supplies: 'supplies',
  acquiring: 'acquiring',
  fixed: 'fixed',
  taxes: 'taxes',
  net: 'net',
}
const LIGHT: ReadonlySet<PriceBarKey> = new Set(['acquiring', 'fixed'])
/** A share below this is not drawn (the legend keeps it); a share from SHOW_LABEL_PCT gets its number inside. */
const MIN_DRAWN_PCT = 0.5
const SHOW_LABEL_PCT = 6

const MISSING_COST_PREFIX = 'Нет цены закупки: '

/** Names of the items without a purchase price, as the API writes them into `details` of a part. */
export function itemsWithoutCost(part: PricePart): string[] {
  return (part.amount?.details ?? []).flatMap((detail) => (detail.label.startsWith(MISSING_COST_PREFIX) ? [detail.label.slice(MISSING_COST_PREFIX.length)] : []))
}

export function entriesOf(parts: PricePart[], net: Figure | null, netShare: Figure | null, netLabel: string): PriceBarEntry[] {
  const known = parts.map((part) => ({ key: part.key, label: part.label, amount: part.amount, share: part.share_pct, incomplete: itemsWithoutCost(part).length > 0 }))
  return [...known, { key: 'net' as const, label: netLabel, amount: net, share: netShare }]
}

export function priceBarAriaLabel(price: Figure, entries: PriceBarEntry[]): string {
  const words = entries.map((entry) => `${entry.label.toLowerCase()} ${entry.share ? formatFigure(entry.share) : 'не заполнено'}`)
  return `Из чего состоит цена ${formatFigure(price)}: ${words.join(', ')}`
}

interface PriceBarProps {
  entries: PriceBarEntry[]
  price: Figure
  /** The service works at a loss: widths follow the sums of the parts and the caption says by how much. */
  loss: boolean
  /** Some part has no sum: the empty track gets the words "не хватает данных". */
  incomplete: boolean
  caption: ReactNode
}

function isDrawn(entry: PriceBarEntry, loss: boolean): boolean {
  if (loss && entry.key === 'net') return false
  if (!entry.amount || !entry.share) return false
  return loss ? entry.amount.value > 0 : entry.share.value >= MIN_DRAWN_PCT
}

/** The bar of the price structure (design/components.md, section 28). Widths come from the API; nothing is added up here. */
export function PriceBar({ entries, price, loss, incomplete, caption }: PriceBarProps) {
  const drawn = entries.filter((entry) => isDrawn(entry, loss))
  return (
    <div className="pbar" data-testid="price-structure">
      <h3 className="pbar__caption">{caption}</h3>
      <div className="pbar__row">
        <div className="pbar__bar" role="img" aria-label={priceBarAriaLabel(price, entries)} data-testid="price-bar" data-loss={loss || undefined}>
          {drawn.map((entry) => {
            const share = entry.share?.value ?? 0
            const style = loss ? { flexGrow: entry.amount?.value ?? 0, flexBasis: 0 } : { flexBasis: `${share}%`, flexGrow: 0 }
            return (
              <i
                key={entry.key}
                className={`pbar__seg pbar__seg--${COLOR_INDEX[entry.key]}${LIGHT.has(entry.key) ? ' pbar__seg--light' : ''}`}
                style={style}
                data-testid="price-bar-segment"
                data-key={entry.key}
              >
                {!loss && share >= SHOW_LABEL_PCT && entry.share && <span className="pbar__seg-text" aria-hidden="true" data-no-tip>{formatPercent(entry.share.value)}</span>}
              </i>
            )
          })}
        </div>
        {incomplete && <span className="pbar__rest">не хватает данных</span>}
      </div>
    </div>
  )
}

interface PriceLegendProps {
  entries: PriceBarEntry[]
  /** Extra line under a part (for the part "fixed": the length of the visit). */
  extras?: Partial<Record<PriceBarKey, ReactNode>>
}

/** The legend of the bar: every sum and every share opens its tip; a part without a sum says so in words. */
export function PriceLegend({ entries, extras = {} }: PriceLegendProps) {
  return (
    <ul className="plegend">
      {entries.map((entry) => (
        <li key={entry.key} className="plegend__item" data-key={entry.key}>
          <span className={`plegend__dot pbar__seg--${COLOR_INDEX[entry.key]}${LIGHT.has(entry.key) ? ' pbar__seg--light' : ''}`} aria-hidden="true" />
          <span className="plegend__name">{entry.label}</span>
          {entry.amount ? (
            <span
              className="plegend__sum"
              data-testid="price-legend-item"
              data-key={entry.key}
              data-figure={entry.key === 'net' ? 'net_profit' : `parts.${entry.key}.amount`}
            >
              <FigureButton figure={entry.amount} title={entry.label} spokenValue={`${entry.label}, ${formatFigure(entry.amount)}`} />
              {entry.incomplete && (
                <span data-testid="price-part-warning" data-key={entry.key}>
                  <Pill variant="neutral">не заполнено</Pill>
                </span>
              )}
            </span>
          ) : (
            <span className="plegend__sum" data-testid="price-legend-item" data-key={entry.key}>
              <span className="plegend__none">—</span>
              <span data-testid="price-part-warning" data-key={entry.key}>
                <Pill variant="neutral">не заполнено</Pill>
              </span>
            </span>
          )}
          {entry.share && entry.amount && (
            <span className="plegend__share" data-testid="price-legend-share" data-key={entry.key} data-figure={entry.key === 'net' ? 'net_margin_pct' : `parts.${entry.key}.share_pct`}>
              <FigureButton figure={entry.share} title={`${entry.label} · доля цены`} spokenValue={`${entry.label}, доля цены ${formatFigure(entry.share)}`} />
            </span>
          )}
          {extras[entry.key] && <span className="plegend__extra">{extras[entry.key]}</span>}
        </li>
      ))}
    </ul>
  )
}

export function PriceBarSkeleton() {
  return (
    <div className="pbar" aria-hidden="true" data-testid="price-structure-loading">
      <div className="pbar__bar pbar__bar--skeleton" />
      <ul className="plegend">
        {Array.from({ length: 8 }, (_, index) => (
          <li key={index} className="plegend__skeleton" />
        ))}
      </ul>
    </div>
  )
}
