import type { BalanceTrendInfo, Figure, TrendPoint } from '../api/types'
import { formatDays, formatFigure, formatSigned } from '../lib/format'
import { BalanceChart } from './BalanceChart'
import { FigureButton } from './FigureButton'
import { FigureTip } from './FigureTip'
import './BalanceHero.css'

interface BalanceHeroProps {
  total: Figure
  /** Change over the week in rubles; absent when the clinic has no history for 7 days. */
  weekChange?: Figure | null
  /** The same change in percent. */
  weekChangePct?: Figure | null
  trend?: TrendPoint[]
  trendInfo?: BalanceTrendInfo
}

const WEEK_TITLE = 'Изменение за неделю'

type Tone = 'up' | 'down' | 'flat'

/** Colour follows the sign the API gave; the sign and the words repeat it, so colour is never alone. */
function toneOf(value: number): Tone {
  if (value > 0) return 'up'
  return value < 0 ? 'down' : 'flat'
}

function totalHint(value: number): { text: string; tone: 'bad' | 'soft' } | null {
  if (value < 0) return { text: 'ниже нуля', tone: 'bad' }
  if (value === 0) return { text: 'на счетах пусто', tone: 'soft' }
  return null
}

function WeekChange({ rub, pct }: { rub?: Figure | null; pct?: Figure | null }) {
  if (!rub && !pct) return null
  const main = rub ?? pct
  if (!main) return null
  const unchanged = (rub?.value ?? 0) === 0 && (pct?.value ?? 0) === 0
  const tone = toneOf(main.value)

  if (unchanged) {
    return (
      <div className="hero__delta hero__delta--flat" data-testid="balance-week-change">
        <FigureButton
          figure={main}
          title={WEEK_TITLE}
          emoji="📈"
          figureKey={rub ? 'balance.week_change' : 'balance.week_change_pct'}
          spokenValue={`${WEEK_TITLE}: без изменений`}
        >
          без изменений за неделю
        </FigureButton>
      </div>
    )
  }

  return (
    <div className={`hero__delta hero__delta--${tone}`} data-testid="balance-week-change">
      {rub && (
        <FigureButton
          figure={rub}
          title={WEEK_TITLE}
          emoji="📈"
          figureKey="balance.week_change"
          spokenValue={`${WEEK_TITLE}, ${formatSigned(rub.value, rub.unit)}`}
        >
          {formatSigned(rub.value, rub.unit)}
          {pct ? '' : ' за неделю'}
        </FigureButton>
      )}
      {rub && pct && <span aria-hidden="true"> · </span>}
      {pct && (
        <FigureButton
          figure={pct}
          title={`${WEEK_TITLE}, %`}
          emoji="📈"
          figureKey="balance.week_change_pct"
          spokenValue={`${WEEK_TITLE}, ${formatSigned(pct.value, pct.unit)}`}
        >
          {formatSigned(pct.value, pct.unit)} за неделю
        </FigureButton>
      )}
    </div>
  )
}

/** The main number of the dashboard with the week change and the 14-day chart (design/components.md, section 15). */
export function BalanceHero({ total, weekChange, weekChangePct, trend, trendInfo }: BalanceHeroProps) {
  const text = formatFigure(total)
  const hint = totalHint(total.value)
  const days = trend?.length ?? 0
  return (
    <section className="hero" data-testid="balance-hero" role="group" aria-label="Остаток на счетах">
      <div className="hero__top">
        <div data-testid="balance-total">
          <FigureTip figure={total} title="Остаток на счетах" emoji="💰">
            {(triggerProps) => (
              <button
                {...triggerProps}
                type="button"
                className="hero__total"
                data-figure="balance.total"
                aria-label={`Остаток на счетах, ${text}`}
              >
                <span className="hero__label">Остаток на счетах</span>
                <span className="hero__num">{text}</span>
                {hint && <span className={`hero__hint hero__hint--${hint.tone}`}>{hint.text}</span>}
              </button>
            )}
          </FigureTip>
        </div>
        {days >= 2 && <span className="hero__cap">Остаток на конец дня, {formatDays(days)}</span>}
      </div>
      <WeekChange rub={weekChange} pct={weekChangePct} />
      <BalanceChart points={trend} info={trendInfo} />
    </section>
  )
}

export function BalanceHeroSkeleton() {
  return (
    <section className="hero hero--loading" data-testid="balance-hero-loading" aria-hidden="true">
      <span className="hero__skeleton hero__skeleton--label" />
      <span className="hero__skeleton hero__skeleton--num" />
      <span className="hero__skeleton hero__skeleton--delta" />
      <span className="hero__skeleton hero__skeleton--chart" />
    </section>
  )
}
