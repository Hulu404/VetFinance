import { useEffect, useRef, type ReactNode, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useServiceCost } from '../../api/queries'
import type { ServiceCost } from '../../api/types'
import { entriesOf, itemsWithoutCost, PriceBar, PriceBarSkeleton, PriceLegend, type PriceBarEntry } from '../../components/PriceBar'
import { FigureButton } from '../../components/FigureButton'
import { Pill } from '../../components/Pill'
import { LoadErrorCard } from '../../components/StateBlocks'
import { formatMonthGenitiveYear } from '../../lib/dates'
import { formatMoney } from '../../lib/format'
import { itemNoCostText, MISSING_TEXT, visitsText } from './priceView'
import '../../components/Banner.css'

const EFFICIENCY_ROUTE = '/analytics/efficiency'
const STOCK_ROUTE = '/reports/stock'
const IMPORT_ROUTE = '/transactions?import=1'
function missingText(kind: ServiceCost['missing'][number], names: string[]): string {
  return kind === 'item_no_cost' ? itemNoCostText(names) : MISSING_TEXT[kind]
}

interface PriceCardProps {
  id: string
  asOf: string | null
  onClose: () => void
  focusRecipe: boolean
  onFocused: () => void
  onEditRecipe: (name: string) => void
  onEditService: (cost: ServiceCost) => void
  onMissing: () => void
}

function MissingBanner({ cost, onEditRecipe }: { cost: ServiceCost; onEditRecipe: () => void }) {
  if (cost.missing.length === 0) return null
  const names = cost.parts.flatMap(itemsWithoutCost)
  return (
    <div className="banner banner--warning pcard__missing" role="status" data-testid="price-card-missing" data-missing={cost.missing.join(' ')}>
      <ul className="pcard__missing-list">
        {cost.missing.map((kind) => (
          <li key={kind} className="pcard__missing-item">
            <span>{missingText(kind, names)}</span>
            {kind === 'recipe' && (
              <button type="button" className="btn btn--primary btn--sm" onClick={onEditRecipe}>
                Заполнить техкарту
              </button>
            )}
            {kind === 'hour_cost' && (
              <Link className="banner__action" to={EFFICIENCY_ROUTE}>
                Открыть эффективность
              </Link>
            )}
            {kind === 'no_expenses' && (
              <Link className="banner__action" to={IMPORT_ROUTE}>
                Загрузить выписку
              </Link>
            )}
            {kind === 'item_no_cost' && (
              <Link className="banner__action" to={STOCK_ROUTE}>
                Открыть склад
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Money({ figure, title, figureKey, testId, tone }: { figure: ServiceCost['price']; title: string; figureKey: string; testId: string; tone?: 'ok' | 'bad' }) {
  return (
    <span className={tone ? `pcard__num pcard__num--${tone}` : 'pcard__num'} data-testid={testId} data-figure={figureKey}>
      <FigureButton figure={figure} title={title} />
    </span>
  )
}

function Head({ cost }: { cost: ServiceCost }) {
  const net = cost.net_profit
  const margin = cost.net_margin_pct
  const loss = net !== null && net.value < 0
  return (
    <div className="pcard__figures">
      <div className="pcard__figure">
        <Money figure={cost.price} title="Цена для клиента" figureKey="price" testId="price-card-price" />
        <span className="pcard__cap">цена для клиента</span>
      </div>
      <div className="pcard__figure pcard__figure--end">
        {net ? (
          <>
            <span className="pcard__net">
              <Money figure={net} title="Чистая прибыль" figureKey="net_profit" testId="price-card-net" tone={loss ? 'bad' : 'ok'} />
              {loss && <Pill variant="danger">в минус</Pill>}
            </span>
            <span className="pcard__cap">
              чистая прибыль
              {margin && (
                <>
                  {' · '}
                  <span data-testid="price-card-net-pct" data-figure="net_margin_pct">
                    <FigureButton figure={margin} title="Чистая маржа" />
                  </span>
                </>
              )}
            </span>
          </>
        ) : (
          <>
            <span className="pcard__num" data-testid="price-card-net">—</span>
            <span className="pcard__cap">чистая прибыль</span>
          </>
        )}
      </div>
    </div>
  )
}

function Structure({ cost, onEditRecipe }: { cost: ServiceCost; onEditRecipe: () => void }) {
  if (cost.status === 'no_recipe' || cost.net_profit === null) {
    const known: PriceBarEntry[] = entriesOf(cost.parts, null, null, 'Чистая прибыль').filter((entry) => entry.key !== 'net')
    return (
      <>
        <p className="pcard__nobar">{cost.missing.includes('recipe') ? 'Полоса появится, когда будет техкарта' : 'Полоса появится, когда будут расходы за месяц'}</p>
        <PriceLegend entries={known} extras={minutesExtras(cost, onEditRecipe)} />
      </>
    )
  }
  const entries = entriesOf(cost.parts, cost.net_profit, cost.net_margin_pct, 'Чистая прибыль')
  const loss = (cost.net_profit?.value ?? 0) < 0
  const incomplete = entries.some((entry) => entry.amount === null || entry.incomplete)
  const caption: ReactNode =
    loss && cost.net_profit ? (
      <>
        Расходы больше цены на{' '}
        <FigureButton figure={cost.net_profit} title="Чистая прибыль" tipValue={formatMoney(cost.net_profit.value)} spokenValue={`Чистая прибыль: ${formatMoney(cost.net_profit.value)}`}>
          {formatMoney(Math.abs(cost.net_profit.value))}
        </FigureButton>
        . Доли в расходах
      </>
    ) : (
      'Из чего состоит цена'
    )
  return (
    <>
      <PriceBar entries={entries} price={cost.price} loss={loss} incomplete={incomplete} caption={caption} />
      <PriceLegend entries={entries} extras={minutesExtras(cost, onEditRecipe)} />
    </>
  )
}

/** The line under "Постоянные": the length of the visit is the clinic average, not the own one of the service. */
function minutesExtras(cost: ServiceCost, onEditRecipe: () => void): Partial<Record<'fixed', ReactNode>> {
  if (cost.minutes_source !== 'clinic_average') return {}
  return {
    fixed: (
      <>
        <span data-testid="price-minutes-note">длительность средняя по клинике, {cost.minutes} мин</span>{' '}
        <button type="button" className="btn btn--text pcard__own" data-testid="price-minutes-own" onClick={onEditRecipe}>
          Указать свою
        </button>
      </>
    ),
  }
}

interface BodyProps {
  cost: ServiceCost
  headingRef: RefObject<HTMLHeadingElement | null>
  onClose: () => void
  onEditRecipe: () => void
  onEditService: () => void
}

function MonthlyLine({ cost }: { cost: ServiceCost }) {
  const { monthly_profit: monthly, net_profit: net } = cost
  if (!monthly || !net) {
    return (
      <p className="pcard__monthly" data-testid="price-card-monthly">
        Приносит клинике —
      </p>
    )
  }
  return (
    <p className="pcard__monthly" data-testid="price-card-monthly" data-figure="monthly_profit">
      Приносит клинике <FigureButton figure={monthly} title="Приносит клинике в месяц" /> в месяц:{' '}
      <FigureButton figure={cost.visits_month} title="Оказана за месяц">
        {visitsText(cost.visits_month.value, cost.service.unit_label)}
      </FigureButton>{' '}
      по <FigureButton figure={net} title="Чистая прибыль одной услуги" />
    </p>
  )
}

function CardBody({ cost, headingRef, onClose, onEditRecipe, onEditService }: BodyProps) {
  const manual = cost.service.source === 'manual'
  const net = cost.net_profit
  const title = [cost.service.group, cost.service.name].filter(Boolean).join(' / ')
  return (
    <>
      <header className="pcard__head">
        <div className="pcard__titles">
          <h2 id="price-card-title" className="pcard__title" ref={headingRef} tabIndex={-1}>
            {title}
          </h2>
          <span data-testid="price-source" data-source={cost.service.source}>
            <Pill variant="neutral">{manual ? 'добавлена вручную' : 'из Ветменеджера'}</Pill>
          </span>
        </div>
        <button type="button" className="btn" data-testid="price-card-close" onClick={onClose}>
          Закрыть
        </button>
      </header>
      <Head cost={cost} />
      {net && net.value < 0 && <p className="pcard__loss-note">{net.note}</p>}
      <MissingBanner cost={cost} onEditRecipe={onEditRecipe} />
      <Structure cost={cost} onEditRecipe={onEditRecipe} />
      <MonthlyLine cost={cost} />
      <p className="pcard__basis" data-testid="price-card-basis">
        Налоги, эквайринг и стоимость часа за {formatMonthGenitiveYear(cost.basis_month)}
      </p>
      <div className="pcard__actions">
        <button type="button" className="btn" data-testid="price-card-edit" onClick={onEditRecipe}>
          Техкарта и параметры
        </button>
        {manual && (
        <button type="button" className="btn btn--text" data-testid="price-service-edit" onClick={onEditService}>
          Изменить услугу
        </button>
        )}
      </div>
    </>
  )
}

export function PriceCard({ id, asOf, focusRecipe, onFocused, onClose, onEditRecipe, onEditService, onMissing }: PriceCardProps) {
  const query = useServiceCost(id, asOf)
  const headingRef = useRef<HTMLHeadingElement | null>(null)
  const sectionRef = useRef<HTMLElement | null>(null)
  const cost = query.data
  const missing = isApiError(query.error) && query.error.kind === 'not_found'
  const loadedId = cost?.service.id

  useEffect(() => {
    if (missing) onMissing()
  }, [missing, onMissing])

  useEffect(() => {
    if (!loadedId) return
    const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    sectionRef.current?.scrollIntoView?.({ block: 'start', behavior: reduce ? 'auto' : 'smooth' })
    const button = focusRecipe ? sectionRef.current?.querySelector<HTMLElement>('[data-testid="price-card-missing"] .btn--primary') : null
    if (button) {
      button.focus({ preventScroll: true })
      onFocused()
    } else {
      headingRef.current?.focus({ preventScroll: true })
    }
  }, [loadedId]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section ref={sectionRef} className="pcard" data-testid="price-card" data-id={id} data-status={cost?.status ?? 'loading'} aria-labelledby="price-card-title" aria-busy={query.isFetching}>
      {cost && <CardBody cost={cost} headingRef={headingRef} onClose={onClose} onEditRecipe={() => onEditRecipe(cost.service.name)} onEditService={() => onEditService(cost)} />}
      {!cost && (
        <>
          <header className="pcard__head">
            <h2 id="price-card-title" className="pcard__title" ref={headingRef} tabIndex={-1}>
              {query.isPending ? <span className="pcard__sk pcard__sk--title" aria-hidden="true" /> : 'Разбор услуги'}
            </h2>
            <button type="button" className="btn" data-testid="price-card-close" onClick={onClose}>
              Закрыть
            </button>
          </header>
          {query.isPending && (
            <div data-testid="price-card-loading">
              <p className="sr-only" role="status">
                Загружаем разбор услуги
              </p>
              <div className="pcard__figures" aria-hidden="true">
                <span className="pcard__sk pcard__sk--num" />
                <span className="pcard__sk pcard__sk--num" />
              </div>
              <PriceBarSkeleton />
            </div>
          )}
          {query.isError && !missing && (
            <LoadErrorCard
              testId="price-card-error"
              title="Не получилось загрузить разбор услуги"
              network={isApiError(query.error) && query.error.kind === 'network'}
              retrying={query.isFetching}
              onRetry={() => void query.refetch()}
            />
          )}
        </>
      )}
    </section>
  )
}
