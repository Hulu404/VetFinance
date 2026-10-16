import type { NormBounds, NormItem } from '../../api/types'
import type { GaugeTone } from '../../components/NormGauge'
import type { PillVariant } from '../../components/Pill'
import type { TipFigure } from '../../components/FigureTip'
import { formatNormRange, formatPercent, formatPp } from '../../lib/format'

/** Words of the deviation pill: the API decides `status`, the client only says it (design/screens/norm.md, "Статусы"). */
export function deviationWords(item: NormItem): string | null {
  if (!item.status || item.status === 'no_norm' || !item.deviation_pp) return null
  const points = formatPp(Math.abs(item.deviation_pp.value))
  if (item.status === 'above') return `выше нормы на ${points}`
  if (item.status === 'below') return `ниже нормы на ${points}`
  return 'в норме'
}

const TONE_PILL: Record<GaugeTone, PillVariant> = {
  good: 'success',
  bad: 'danger',
  warn: 'warning',
  neutral: 'neutral',
}

export function pillVariantFor(tone: NormItem['tone']): PillVariant {
  return tone ? TONE_PILL[tone] : 'neutral'
}

export function rangeOf(item: NormItem): string | null {
  return item.norm ? formatNormRange(item.norm.min_pct, item.norm.max_pct) : null
}

/** The norm as a figure for the tip: border sums in rubles, the note and the origin of the norm. */
export function normTipFigure(norm: NormBounds): TipFigure {
  return {
    value: norm.max_pct ?? norm.min_pct ?? 0,
    unit: 'pct',
    breakdown: norm.breakdown ?? [],
    source: [norm.source],
    note: norm.note ?? '',
  }
}

/** "Норма 22–28%, у вас 24,6%: в норме" for the gauge. */
export function gaugeLabel(item: NormItem): string {
  const range = rangeOf(item) ?? 'не задана'
  const words = deviationWords(item) ?? 'без оценки'
  return `Норма ${range}, у вас ${formatPercent(item.actual_pct.value)}: ${words}`
}

/** A row can be judged only when the API gave a status; in an open month it does not. */
export function isComparable(item: NormItem): boolean {
  return item.status !== undefined && item.status !== null && item.status !== 'no_norm'
}
