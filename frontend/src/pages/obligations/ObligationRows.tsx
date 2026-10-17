import type { ReactNode } from 'react'
import type { Equipment, Loan } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { PaidProgress } from '../../components/PaidProgress'
import { Pill } from '../../components/Pill'
import { formatMoney } from '../../lib/format'
import { formatMonthGenitiveYear, formatMonthYear } from '../../lib/dates'
import { formatRate, yearsText } from '../../lib/planning'

const DASH = '—'

/** "Сбербанк · 12% · 10-го · до ноября 2028" / "лизинг · 10-го · до февраля 2028"; a closed one says since when. */
export function loanMeta(loan: Loan): string {
  const parts: string[] = []
  if (loan.kind === 'lease') parts.push(loan.lender ? `лизинг, ${loan.lender}` : 'лизинг')
  else if (loan.lender) parts.push(loan.lender)
  if (loan.kind === 'loan' && loan.rate_pct !== null) parts.push(formatRate(loan.rate_pct))
  parts.push(`${loan.payment_day}-го`)
  if (loan.status === 'closed' && loan.closed_from) parts.push(`закрыт с ${formatMonthGenitiveYear(loan.closed_from)}`)
  else parts.push(`до ${formatMonthGenitiveYear(loan.last_payment_month)}`)
  return parts.join(' · ')
}

export function equipmentMeta(item: Equipment): { years: string; period: string } {
  return {
    years: yearsText(item.life_years),
    period:
      item.status === 'closed' && item.closed_from
        ? `закрыт с ${formatMonthGenitiveYear(item.closed_from)}`
        : `${formatMonthYear(item.amortization_from)} – ${formatMonthYear(item.amortization_to)}`,
  }
}

/** "выплачен" / "срок вышел" / "закрыт": a word in a pill, the colour says nothing. */
export function StatusPill({ status, kind }: { status: Loan['status']; kind: 'loan' | 'equipment' }) {
  if (status === 'active') return null
  const label = status === 'closed' ? 'закрыт' : kind === 'equipment' ? 'срок вышел' : 'выплачен'
  return (
    <span data-testid="obligations-status-pill" data-status={status}>
      <Pill variant="neutral">{label}</Pill>
    </span>
  )
}

interface RowActions {
  onEdit: (item: Loan | Equipment, opener: HTMLElement) => void
}

function EditButton({ item, onEdit }: { item: Loan | Equipment; onEdit: RowActions['onEdit'] }) {
  if (item.status === 'closed') return null
  return (
    <button
      type="button"
      className="btn btn--text obl__edit"
      data-testid="obligations-edit"
      aria-label={`Изменить: ${item.name}`}
      onClick={(event) => onEdit(item, event.currentTarget)}
    >
      Изменить
    </button>
  )
}

function Amount({ testId, figure, title, figureKey, closed, suffix = '' }: { testId: string; figure: Loan['remaining']; title: string; figureKey: string; closed: boolean; suffix?: string }) {
  if (closed) return <span className="obl__none">{DASH}</span>
  return (
    <span data-testid={testId}>
      <FigureButton figure={figure} title={title} figureKey={figureKey} spokenValue={`${title}: ${formatMoney(figure.value)}`}>
        {formatMoney(figure.value)}
        {suffix}
      </FigureButton>
    </span>
  )
}

function LoanProgress({ loan, index }: { loan: Loan; index: number }) {
  if (loan.status === 'closed') return null
  return (
    <div data-testid="obligations-loan-progress" className="obl__progress">
      <PaidProgress
        figure={loan.paid_pct}
        status={loan.status}
        figureKey={`loans.${index}.paid_pct`}
        title={`${loan.name} · выплачено`}
        pillTestId="obligations-status-pill"
      />
    </div>
  )
}

function LoanName({ loan }: { loan: Loan }) {
  return (
    <>
      <span className="obl__name">
        {loan.name} {loan.status === 'closed' && <StatusPill status={loan.status} kind="loan" />}
      </span>
      <span className="obl__meta">{loanMeta(loan)}</span>
    </>
  )
}

function rowAttributes(item: Loan | Equipment) {
  return { 'data-id': item.id, 'data-status': item.status }
}

/** Wide screens: a table of loans and leases. */
export function LoansTable({ loans, onEdit }: { loans: Loan[] } & RowActions) {
  return (
    <table className="obl__table">
      <caption className="sr-only">Кредиты и лизинг</caption>
      <thead>
        <tr>
          <th scope="col">Что</th>
          <th scope="col">Прогресс</th>
          <th scope="col" className="obl__num">Осталось</th>
          <th scope="col" className="obl__num">Платёж</th>
          <th scope="col"><span className="sr-only">Действия</span></th>
        </tr>
      </thead>
      <tbody>
        {loans.map((loan, index) => (
          <tr key={loan.id} className="obl__row" data-testid="obligations-loan-row" data-kind={loan.kind} {...rowAttributes(loan)}>
            <th scope="row" className="obl__what">
              <LoanName loan={loan} />
            </th>
            <td><LoanProgress loan={loan} index={index} /></td>
            <td className="obl__num">
              <Amount testId="obligations-loan-remaining" figure={loan.remaining} title={`${loan.name} · осталось`} figureKey={`loans.${index}.remaining`} closed={loan.status === 'closed'} />
            </td>
            <td className="obl__num">
              <Amount testId="obligations-loan-payment" figure={loan.payment} title={`${loan.name} · платёж`} figureKey={`loans.${index}.payment`} closed={loan.status === 'closed'} />
            </td>
            <td className="obl__act"><EditButton item={loan} onEdit={onEdit} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Up to 1100px: a card per loan (a separate markup, not a table turned into blocks). */
export function LoansCards({ loans, onEdit }: { loans: Loan[] } & RowActions) {
  return (
    <ul className="obl__cards">
      {loans.map((loan, index) => (
        <li key={loan.id} className="obl__card" data-testid="obligations-loan-row" data-kind={loan.kind} {...rowAttributes(loan)}>
          <div className="obl__card-head">
            <span className="obl__what"><LoanName loan={loan} /></span>
            <EditButton item={loan} onEdit={onEdit} />
          </div>
          <LoanProgress loan={loan} index={index} />
          <dl className="obl__pair">
            <div>
              <dt>Осталось</dt>
              <dd>
                <Amount testId="obligations-loan-remaining" figure={loan.remaining} title={`${loan.name} · осталось`} figureKey={`loans.${index}.remaining`} closed={loan.status === 'closed'} />
              </dd>
            </div>
            <div>
              <dt>Платёж</dt>
              <dd>
                <Amount testId="obligations-loan-payment" figure={loan.payment} title={`${loan.name} · платёж`} figureKey={`loans.${index}.payment`} closed={loan.status === 'closed'} />
              </dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  )
}

function EquipmentName({ item, index }: { item: Equipment; index: number }) {
  const meta = equipmentMeta(item)
  return (
    <>
      <span className="obl__name">
        {item.name} <StatusPill status={item.status} kind="equipment" />
      </span>
      <span className="obl__meta">
        <span data-testid="obligations-equipment-cost">
          <FigureButton figure={item.cost} title={`${item.name} · стоимость`} figureKey={`equipment.${index}.cost`} />
        </span>
        {` · ${meta.years} · ${meta.period}`}
      </span>
    </>
  )
}

function MonthlyAmount({ item, index }: { item: Equipment; index: number }): ReactNode {
  if (item.status !== 'active') return <span className="obl__none">{DASH}</span>
  return (
    <span data-testid="obligations-equipment-monthly">
      <FigureButton
        figure={item.monthly}
        title={`${item.name} · в месяц`}
        figureKey={`equipment.${index}.monthly`}
        spokenValue={`${item.name}: ${formatMoney(item.monthly.value)} в месяц`}
      >
        {formatMoney(item.monthly.value)}/мес
      </FigureButton>
    </span>
  )
}

export function EquipmentTable({ equipment, onEdit }: { equipment: Equipment[] } & RowActions) {
  return (
    <table className="obl__table obl__table--equipment">
      <caption className="sr-only">Амортизация оборудования</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">Оборудование</th>
          <th scope="col">В месяц</th>
          <th scope="col">Действия</th>
        </tr>
      </thead>
      <tbody>
        {equipment.map((item, index) => (
          <tr key={item.id} className="obl__row" data-testid="obligations-equipment-row" {...rowAttributes(item)}>
            <th scope="row" className="obl__what"><EquipmentName item={item} index={index} /></th>
            <td className="obl__num"><MonthlyAmount item={item} index={index} /></td>
            <td className="obl__act"><EditButton item={item} onEdit={onEdit} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function EquipmentCards({ equipment, onEdit }: { equipment: Equipment[] } & RowActions) {
  return (
    <ul className="obl__cards">
      {equipment.map((item, index) => (
        <li key={item.id} className="obl__card" data-testid="obligations-equipment-row" {...rowAttributes(item)}>
          <div className="obl__card-head">
            <span className="obl__what"><EquipmentName item={item} index={index} /></span>
            <EditButton item={item} onEdit={onEdit} />
          </div>
          <div className="obl__monthly"><MonthlyAmount item={item} index={index} /></div>
        </li>
      ))}
    </ul>
  )
}
