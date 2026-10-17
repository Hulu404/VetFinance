import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useObligations } from '../../api/queries'
import type { Equipment, Loan, ObligationsReport } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { KpiCard } from '../../components/KpiCard'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { asOfFromSearch } from '../../lib/asOf'
import { monthNameLower } from '../../lib/dates'
import { formatFigure } from '../../lib/format'
import { obligationsCountText } from '../../lib/planning'
import { NARROW_LIST_QUERY, useMediaQuery } from '../../lib/useMediaQuery'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { CloseObligationDialog } from './CloseObligationDialog'
import { ObligationDialog, type ObligationTarget } from './ObligationDialog'
import { EquipmentCards, EquipmentTable, LoansCards, LoansTable } from './ObligationRows'
import './ObligationsPage.css'

const ROW_SKELETONS = 2

interface AddButtonsProps {
  disabled?: boolean
  onAdd: (target: ObligationTarget) => void
  loan?: boolean
  equipment?: boolean
  primaryLoan?: boolean
}

function AddButtons({ disabled = false, onAdd, loan = true, equipment = true, primaryLoan = false }: AddButtonsProps) {
  return (
    <>
      {loan && (
        <button
          type="button"
          className={primaryLoan ? 'btn btn--primary' : 'btn'}
          disabled={disabled}
          data-testid="obligations-add-loan"
          onClick={() => onAdd({ kind: 'new', form: 'loan' })}
        >
          Добавить кредит или лизинг
        </button>
      )}
      {equipment && (
        <button type="button" className="btn" disabled={disabled} data-testid="obligations-add-equipment" onClick={() => onAdd({ kind: 'new', form: 'equipment' })}>
          Добавить оборудование
        </button>
      )}
    </>
  )
}

function Cards({ report }: { report: ObligationsReport }) {
  const activeLoans = report.loans.filter((loan) => loan.status === 'active').length
  const share = report.monthly_payment_share_pct
  return (
    <ul className="kpi-grid kpi-grid--plan" aria-label="Итоги обязательств">
      <li>
        <KpiCard
          label="Всего долг"
          emoji="🏦"
          state="ready"
          figure={report.debt_total}
          figureKey="debt_total"
          valueTestId="obligations-debt"
          subText={report.loans.length === 0 ? 'кредитов нет' : obligationsCountText(activeLoans)}
        />
      </li>
      <li>
        <KpiCard
          label="Платёж в месяц"
          emoji="📆"
          state="ready"
          figure={report.monthly_payment}
          figureKey="monthly_payment"
          valueTestId="obligations-payment"
          subText={share ? undefined : report.loans.length === 0 ? 'платежей нет' : 'кредит и лизинг'}
          extra={
            share ? (
              <span data-testid="obligations-payment-share">
                <FigureButton figure={share} title="Платёж к выручке" figureKey="monthly_payment_share_pct">
                  {formatFigure(share)} выручки
                </FigureButton>
              </span>
            ) : undefined
          }
        />
      </li>
      <li>
        <KpiCard
          label="Амортизация"
          emoji="🔧"
          state="ready"
          figure={report.amortization_month}
          figureKey="amortization_month"
          valueTestId="obligations-amortization"
          valueText={`${formatFigure(report.amortization_month)}/мес`}
          subText={report.equipment.length === 0 ? 'оборудование не внесено' : 'неденежный расход'}
        />
      </li>
    </ul>
  )
}

function PnlLine({ report, asOf }: { report: ObligationsReport; asOf: string | null }) {
  const { month, amount } = report.pnl_month
  const params = new URLSearchParams({ month })
  if (asOf) params.set('as_of', asOf)
  return (
    <p className="obl-pnl">
      <span data-testid="obligations-pnl" data-month={month}>
        В «Прибыли и убытках» за {monthNameLower(month)}:{' '}
        <FigureButton figure={amount} title={`В «Прибыли и убытках» за ${monthNameLower(month)}`} figureKey="pnl_month.amount" />
        {' — проценты, лизинг и амортизация.'}
      </span>
      <Link className="obl-pnl__link" to={`/reports/pnl?${params.toString()}`} data-testid="obligations-pnl-link">
        Открыть отчёт
      </Link>
    </p>
  )
}

interface BlockProps {
  headingId: string
  title: string
  action: ReactNode
  children: ReactNode
}

function Block({ headingId, title, action, children }: BlockProps) {
  return (
    <section className="obl-card" aria-labelledby={headingId}>
      <div className="obl-card__head">
        <h2 id={headingId} className="obl-card__title" tabIndex={-1}>
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function SkeletonRows() {
  return (
    <div aria-hidden="true">
      {Array.from({ length: ROW_SKELETONS }, (_, index) => (
        <div key={index} className="obl-skeleton__row">
          <span className="obl-skeleton__name" />
          <span className="obl-skeleton__bar" />
          <span className="obl-skeleton__sum" />
        </div>
      ))}
    </div>
  )
}

interface BodyProps {
  report: ObligationsReport
  asOf: string | null
  narrow: boolean
  onAdd: (target: ObligationTarget) => void
  onEdit: (item: Loan | Equipment, opener: HTMLElement) => void
}

function ObligationsBody({ report, asOf, narrow, onAdd, onEdit }: BodyProps) {
  const hasLoans = report.loans.length > 0
  const hasEquipment = report.equipment.length > 0
  if (!hasLoans && !hasEquipment) {
    return (
      <EmptyState
        testId="obligations-empty"
        icon="🏦"
        title="Кредитов, лизинга и оборудования пока нет"
        text="Внесите их, чтобы прибыль в отчёте и платежи в календаре были точными. Если кредитов нет, ничего вносить не нужно."
        actions={<AddButtons onAdd={onAdd} primaryLoan />}
      />
    )
  }
  return (
    <>
      <Cards report={report} />
      <PnlLine report={report} asOf={asOf} />
      <Block headingId="obl-loans" title="Кредиты и лизинг" action={<AddButtons onAdd={onAdd} equipment={false} />}>
        {hasLoans ? (
          narrow ? <LoansCards loans={report.loans} onEdit={onEdit} /> : <LoansTable loans={report.loans} onEdit={onEdit} />
        ) : (
          <p className="obl-card__none">Кредитов и лизинга нет.</p>
        )}
        <p className="footnote">Платежи стоят в платёжном календаре в свой день.</p>
      </Block>
      <Block headingId="obl-equipment" title="Амортизация оборудования" action={<AddButtons onAdd={onAdd} loan={false} />}>
        {hasEquipment ? (
          narrow ? <EquipmentCards equipment={report.equipment} onEdit={onEdit} /> : <EquipmentTable equipment={report.equipment} onEdit={onEdit} />
        ) : (
          <p className="obl-card__none">Оборудование не внесено.</p>
        )}
        <p className="footnote">
          Амортизация не списывает деньги со счёта, но показывает реальную стоимость работы оборудования. Без неё прибыль выглядит выше, чем есть.
          Оборудование в лизинге не амортизируется: платёж по лизингу уже в расходах.
        </p>
      </Block>
    </>
  )
}

export function ObligationsPage() {
  const [search] = useSearchParams()
  const asOf = asOfFromSearch(search.toString())
  const query = useObligations(asOf)
  const toast = useToast()
  const narrow = useMediaQuery(NARROW_LIST_QUERY)
  const [form, setForm] = useState<ObligationTarget | null>(null)
  const [closing, setClosing] = useState<Loan | Equipment | null>(null)
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const failedWithoutData = query.isError && !data
  const today = data?.as_of ?? ''
  const closeForm = () => setForm(null)
  const focusBlock = () => document.getElementById('obl-loans')?.focus()

  return (
    <div data-testid="obligations" aria-busy={loading || (query.isFetching && Boolean(data))}>
      <PageHeader title="Обязательства" subtitle="Кредиты, лизинг и амортизация оборудования" balance />
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {loading && (
        <div data-testid="obligations-loading">
          <p className="sr-only" role="status">
            Загружаем обязательства
          </p>
          <ul className="kpi-grid kpi-grid--plan" aria-hidden="true">
            {['🏦', '📆', '🔧'].map((emoji) => (
              <li key={emoji}>
                <KpiCard label="" emoji={emoji} state="loading" />
              </li>
            ))}
          </ul>
          <span className="obl-skeleton__line" aria-hidden="true" />
          <Block headingId="obl-loans" title="Кредиты и лизинг" action={<AddButtons onAdd={setForm} equipment={false} disabled />}>
            <SkeletonRows />
          </Block>
          <Block headingId="obl-equipment" title="Амортизация оборудования" action={<AddButtons onAdd={setForm} loan={false} disabled />}>
            <SkeletonRows />
          </Block>
        </div>
      )}
      {failedWithoutData && (
        <LoadErrorCard
          testId="obligations-error"
          retryTestId="obligations-error-retry"
          title="Не получилось загрузить обязательства"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {data && (
        <ObligationsBody
          report={data}
          asOf={asOf}
          narrow={narrow}
          onAdd={setForm}
          onEdit={(item) => setForm({ kind: 'edit', item })}
        />
      )}
      {data && form && (
        <ObligationDialog
          target={form}
          today={today}
          fallbackFocus={focusBlock}
          onClose={closeForm}
          onSaved={(message) => {
            closeForm()
            toast.show({ message })
          }}
          onCloseObligation={setClosing}
        />
      )}
      {data && closing && (
        <CloseObligationDialog
          item={closing}
          month={data.pnl_month.month}
          onClose={() => setClosing(null)}
          onClosed={() => {
            setClosing(null)
            closeForm()
            toast.show({ message: 'Обязательство закрыто' })
          }}
        />
      )}
    </div>
  )
}
