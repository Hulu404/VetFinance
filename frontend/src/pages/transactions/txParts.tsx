import type { Figure, Transaction, TxSource } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { Pill, type PillVariant } from '../../components/Pill'
import { formatDateLong, formatDateShort, formatDayMonth, parseIsoDate } from '../../lib/dates'
import { formatMoney } from '../../lib/format'

export const SOURCE_PILL: Record<TxSource, { text: string; variant: PillVariant }> = {
  bank: { text: 'Банк', variant: 'neutral' },
  vetmanager: { text: 'Ветменеджер', variant: 'vetmanager' },
  manual: { text: 'Вручную', variant: 'neutral' },
  bot: { text: 'Бот', variant: 'bot' },
}

/** The tip of an amount. Without `figure` from the API the tip is built from the fields of the row, without any arithmetic. */
export function amountFigure(tx: Transaction): Figure {
  if (tx.figure) return tx.figure
  const parts = [formatDateLong(tx.date), tx.account.name]
  if (tx.category) parts.push(`статья «${tx.category.name}»`)
  return { value: tx.amount, unit: 'rub', breakdown: [], source: [tx.source], note: parts.join(' · ') }
}

/** "+71 000 ₽" / "−5 400 ₽": the sign duplicates the colour. */
export function signedMoney(amount: number): string {
  return amount > 0 ? `+${formatMoney(amount)}` : formatMoney(amount)
}

export function SourcePill({ source }: { source: TxSource }) {
  const pill = SOURCE_PILL[source]
  return (
    <span data-testid="tx-source">
      <Pill variant={pill.variant}>{pill.text}</Pill>
    </span>
  )
}

export function DateCell({ date, referenceYear }: { date: string; referenceYear: number | undefined }) {
  const parsed = parseIsoDate(date)
  const spoken = parsed && referenceYear !== undefined && parsed.year !== referenceYear ? formatDateLong(date) : formatDayMonth(date)
  return (
    <time dateTime={date} data-testid="tx-date">
      <span aria-hidden="true">{formatDateShort(date, referenceYear)}</span>
      <span className="sr-only">{spoken}</span>
    </time>
  )
}

export function AmountCell({ tx }: { tx: Transaction }) {
  const tone = tx.kind === 'transfer' || tx.status === 'duplicate' ? 'soft' : tx.amount > 0 ? 'in' : 'out'
  return (
    <span className={`tx-amount tx-amount--${tone}`} data-testid="tx-amount">
      <FigureButton figure={amountFigure(tx)} title="Операция" spokenValue={signedMoney(tx.amount)}>
        {signedMoney(tx.amount)}
      </FigureButton>
    </span>
  )
}

/** Description with the 2-line limit; the full text is in the title. */
export function DescriptionText({ tx }: { tx: Transaction }) {
  return (
    <span className="tx-desc" data-testid="tx-description" title={tx.description}>
      {tx.description}
    </span>
  )
}

/** "Т-Банк · 7972 · Банк" under the description. */
export function MetaLine({ tx }: { tx: Transaction }) {
  return (
    <span className="tx-meta">
      {tx.account.name} · {SOURCE_PILL[tx.source].text}
    </span>
  )
}

interface CategoryCellProps {
  tx: Transaction
  /** "all": the pill opens the dialog. "check": the action column has the button, the pill is only a label. */
  mode: 'all' | 'check'
  disabled?: boolean
  onEdit: (tx: Transaction) => void
}

/** The "Статья" column: the pill that says what the operation is (design/components.md, section 3). */
export function CategoryCell({ tx, mode, disabled = false, onEdit }: CategoryCellProps) {
  if (tx.kind === 'transfer') return <Pill variant="neutral">перевод между счетами</Pill>

  if (tx.status === 'check') {
    const label = (
      <Pill variant="danger">
        без статьи<span className="sr-only">, на проверку</span>
      </Pill>
    )
    if (mode === 'check') return <span data-testid="tx-status">{label}</span>
    return (
      <span data-testid="tx-status">
        <button
          type="button"
          className="tx-pillbtn"
          data-testid="tx-category"
          disabled={disabled}
          aria-label={`Статья: без статьи. Выбрать для операции «${tx.description}»`}
          onClick={() => onEdit(tx)}
        >
          {label}
        </button>
      </span>
    )
  }

  if (!tx.category) return <span className="tx-none">—</span>

  if (tx.status === 'duplicate') {
    return (
      <span data-testid="tx-category">
        <Pill variant="neutral">{tx.category.name}</Pill>
      </span>
    )
  }

  return (
    <button
      type="button"
      className="tx-pillbtn"
      data-testid="tx-category"
      disabled={disabled}
      aria-label={`Статья: ${tx.category.name}. Изменить`}
      onClick={() => onEdit(tx)}
    >
      <Pill variant="neutral">{tx.category.name}</Pill>
    </button>
  )
}

/** The "дубль" plate next to the description of a confirmed duplicate. */
export function DuplicateMark({ tx }: { tx: Transaction }) {
  if (tx.status !== 'duplicate') return null
  return (
    <span data-testid="tx-status">
      <Pill variant="warning">дубль</Pill>
    </span>
  )
}
