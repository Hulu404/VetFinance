import './NormGauge.css'

export type GaugeTone = 'good' | 'warn' | 'bad' | 'neutral'

interface NormGaugeProps {
  minPct: number | null
  maxPct: number | null
  /** The clinic's own share, `actual_pct.value`. */
  actualPct: number
  /** Colour of the marker, chosen by the API (`tone`); the client does not judge. */
  tone: GaugeTone
  /** Words for a screen reader: "Норма 22–28%, у вас 24,6%: в норме". */
  label: string
}

const MARKER_MIN = 2
const MARKER_MAX = 98
const MAX_SCALE_FACTOR = 1.6
const MIN_SCALE_FACTOR = 2
const ACTUAL_SCALE_FACTOR = 1.25

/** Upper edge of the track (design/components.md, section 19). A drawing scale, not a calculation. */
function scaleTop(minPct: number | null, maxPct: number | null, actualPct: number): number {
  const base = maxPct !== null ? maxPct * MAX_SCALE_FACTOR : (minPct ?? 0) * MIN_SCALE_FACTOR
  return Math.max(base, actualPct * ACTUAL_SCALE_FACTOR, 1)
}

function toPercentOfTrack(value: number, top: number): number {
  return (value / top) * 100
}

/** Where the norm lies and where the clinic is; the numbers live in the cells next to it. */
export function NormGauge({ minPct, maxPct, actualPct, tone, label }: NormGaugeProps) {
  const top = scaleTop(minPct, maxPct, actualPct)
  const hasMin = minPct !== null && minPct > 0
  const zoneStart = hasMin ? toPercentOfTrack(minPct, top) : 0
  const zoneEnd = maxPct !== null ? toPercentOfTrack(maxPct, top) : 100
  const marker = Math.min(Math.max(toPercentOfTrack(Math.max(actualPct, 0), top), MARKER_MIN), MARKER_MAX)
  const zoneClass = `gauge__zone${hasMin ? '' : ' gauge__zone--open-left'}${maxPct === null ? ' gauge__zone--open-right' : ''}`
  return (
    <div className="gauge" role="img" aria-label={label} data-testid="norm-gauge">
      <span className={zoneClass} style={{ left: `${zoneStart}%`, width: `${zoneEnd - zoneStart}%` }} aria-hidden="true" />
      <span className={`gauge__marker gauge__marker--${tone}`} style={{ left: `${marker}%` }} aria-hidden="true" />
    </div>
  )
}
