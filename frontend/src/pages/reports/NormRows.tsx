import type { NormItem } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { NormGauge } from '../../components/NormGauge'
import { Pill } from '../../components/Pill'
import { formatDeltaAware } from '../../lib/format'
import { deviationWords, gaugeLabel, isComparable, normTipFigure, pillVariantFor, rangeOf } from './normView'

const MEMO_TEXT = 'справочно, в сумму долей не входит'
const NO_NORM_TEXT = 'нормы нет'
const AFTER_CLOSE_TEXT = 'сравним после закрытия месяца'

function rowAttrs(item: NormItem) {
  return {
    'data-testid': 'norm-row',
    'data-key': item.key,
    'data-status': item.status ?? undefined,
    'data-tone': item.tone ?? undefined,
    'data-memo': item.memo ? 'true' : undefined,
  }
}

/** Norm corridor as a neutral pill that opens the borders in rubles. */
export function NormPill({ item }: { item: NormItem }) {
  const range = rangeOf(item)
  if (!item.norm || !range) return <span className="norm-nonorm">{NO_NORM_TEXT}</span>
  return (
    <span data-testid="norm-norm" data-figure={`items.${item.key}.norm`}>
      <FigureButton
        figure={normTipFigure(item.norm)}
        title={`${item.label} · норма`}
        tipValue={range}
        spokenValue={`Норма ${range}`}
        className="norm-pillbtn"
      >
        <Pill variant="neutral">{range}</Pill>
      </FigureButton>
    </span>
  )
}

export function ShareButton({ item }: { item: NormItem }) {
  const text = formatDeltaAware(item.actual_pct)
  return (
    <span data-testid="norm-share" data-figure={`items.${item.key}.actual_pct`}>
      <FigureButton figure={item.actual_pct} title={`${item.label} · доля выручки`} spokenValue={`${item.label}, доля выручки ${text}`}>
        {text}
      </FigureButton>
    </span>
  )
}

export function DeviationPill({ item }: { item: NormItem }) {
  const words = deviationWords(item)
  if (!words || !item.deviation_pp) return <span className="norm-dash" data-testid="norm-deviation-pp">—</span>
  return (
    <span data-testid="norm-deviation-pp" data-figure={`items.${item.key}.deviation_pp`}>
      <FigureButton figure={item.deviation_pp} title={`${item.label} · отклонение от нормы`} tipValue={words} spokenValue={`${item.label}: ${words}`}>
        <Pill variant={pillVariantFor(item.tone)}>{words}</Pill>
      </FigureButton>
    </span>
  )
}

export function DeviationRub({ item }: { item: NormItem }) {
  const figure = item.deviation_rub
  if (!figure || !isComparable(item)) return <span className="norm-dash" data-testid="norm-deviation-rub">—</span>
  const text = item.status === 'ok' ? '—' : formatDeltaAware(figure)
  return (
    <span data-testid="norm-deviation-rub" data-figure={`items.${item.key}.deviation_rub`}>
      <FigureButton
        figure={figure}
        title={`${item.label} · отклонение в рублях`}
        spokenValue={item.status === 'ok' ? `${item.label}: отклонения в рублях нет` : `${item.label}: ${text}`}
      >
        {text}
      </FigureButton>
    </span>
  )
}

function Gauge({ item }: { item: NormItem }) {
  if (!item.norm || !isComparable(item)) return <span className="norm-dash">—</span>
  return (
    <NormGauge
      minPct={item.norm.min_pct}
      maxPct={item.norm.max_pct}
      actualPct={item.actual_pct.value}
      tone={item.tone ?? 'neutral'}
      label={gaugeLabel(item)}
    />
  )
}

function NameCell({ item }: { item: NormItem }) {
  return (
    <>
      {item.label}
      {item.memo && <span className="norm-memo">{MEMO_TEXT}</span>}
    </>
  )
}

/** Wide screens: one row of the table. */
export function NormTableRow({ item }: { item: NormItem }) {
  return (
    <tr {...rowAttrs(item)}>
      <th scope="row">
        <NameCell item={item} />
      </th>
      <td className="norm-col-norm">
        <NormPill item={item} />
      </td>
      <td className="norm-col-gauge">
        <Gauge item={item} />
      </td>
      <td className="norm-col-share">
        <ShareButton item={item} />
      </td>
      <td className="norm-col-dev">
        <DeviationPill item={item} />
      </td>
      <td className="norm-col-rub">
        <DeviationRub item={item} />
      </td>
    </tr>
  )
}

/** 1100px and narrower: a card with the same cells (its own markup, not a squeezed table). */
export function NormCard({ item }: { item: NormItem }) {
  const comparable = isComparable(item)
  const hasNorm = Boolean(item.norm)
  return (
    <li className="norm-item" {...rowAttrs(item)}>
      <div className="norm-item__line">
        <span className="norm-item__name">
          <NameCell item={item} />
        </span>
        {hasNorm && <DeviationPill item={item} />}
      </div>
      {comparable && hasNorm && <Gauge item={item} />}
      <div className="norm-item__line">
        <span className="norm-item__value">
          <span className="norm-item__label">Ваша доля </span>
          <ShareButton item={item} />
        </span>
        <span className="norm-item__value">
          <span className="norm-item__label">Норма </span>
          <NormPill item={item} />
        </span>
      </div>
      {comparable && (
        <div className="norm-item__line">
          <span className="norm-item__value">
            <span className="norm-item__label">В рублях </span>
            <DeviationRub item={item} />
          </span>
        </div>
      )}
      {!comparable && hasNorm && <p className="norm-item__label">{AFTER_CLOSE_TEXT}</p>}
    </li>
  )
}
