import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useServices } from '../../api/queries'
import type { ServiceItem, ServiceList, ServiceSort } from '../../api/types'
import { DataStrips } from '../../components/DataStrips'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState, LoadErrorCard } from '../../components/StateBlocks'
import { Segmented } from '../../components/Tabs'
import { useToast } from '../../components/Toast'
import { MOBILE_QUERY, NARROW_LIST_QUERY, useMediaQuery } from '../../lib/useMediaQuery'
import { useSlowLoading } from '../../lib/useSlowLoading'
import { PriceCard } from './PriceCard'
import { PriceCards, PriceTable } from './PriceList'
import { FILTER_EMPTY_TEXT, FILTER_LABELS, servicesCountText, type FilterId } from './priceView'
import { RecipeDialog, type RecipeTarget } from './RecipeDialog'
import { DeleteServiceDialog, ServiceDialog, serviceValuesOf, type ServiceDialogTarget } from './ServiceDialog'
import { usePriceParams } from './usePriceParams'
import './PricePage.css'

const SEARCH_DEBOUNCE_MS = 300
const SKELETON_ROWS = 8
const FILTER_IDS: FilterId[] = ['all', 'loss', 'no_recipe']
const FILTER_TEST_IDS: Record<FilterId, string> = {
  all: 'price-filter-all',
  loss: 'price-filter-loss',
  no_recipe: 'price-filter-no-recipe',
}

function useDebouncedSearch(value: string, apply: (next: string) => void): [string, (next: string) => void] {
  const [text, setText] = useState(value)
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    setText(value)
  }
  useEffect(() => {
    if (text === value) return
    const timer = window.setTimeout(() => apply(text), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [text, value, apply])
  return [text, setText]
}

function Headline({ data, onFill }: { data: ServiceList | undefined; onFill: () => void }) {
  if (!data?.headline) return null
  return (
    <div className="price-headline">
      <p className="headline" data-testid="price-headline">
        {data.headline}
      </p>
      {data.counts.no_recipe > 0 && (
        <button type="button" className="btn btn--primary" onClick={onFill}>
          Заполнить техкарты
        </button>
      )}
    </div>
  )
}

function ListSkeleton() {
  return (
    <div data-testid="price-loading" aria-hidden="true">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="price-skeleton__row">
          <span className="price-skeleton__name" />
          <span className="price-skeleton__num" />
          <span className="price-skeleton__num" />
        </div>
      ))}
    </div>
  )
}

interface ToolbarProps {
  counts: ServiceList['counts'] | null
  filter: FilterId
  sort: ServiceSort
  order: 'asc' | 'desc'
  noRecipes: boolean
  search: string
  disabled: boolean
  onFilter: (filter: FilterId) => void
  onSort: (sort: ServiceSort) => void
  onSearch: (text: string) => void
}

function Toolbar({ counts, filter, sort, order, noRecipes, search, disabled, onFilter, onSort, onSearch }: ToolbarProps) {
  const phone = useMediaQuery(MOBILE_QUERY)
  const options = FILTER_IDS.map((id) => ({
    id,
    label: counts ? `${FILTER_LABELS[id]} ${counts[id]}` : FILTER_LABELS[id],
    testId: FILTER_TEST_IDS[id],
    data: counts ? { 'data-count': String(counts[id]) } : undefined,
  }))
  const ariaSort = (key: ServiceSort) => (sort === key ? (order === 'asc' ? ('ascending' as const) : ('descending' as const)) : ('none' as const))
  return (
    <div className="price-toolbar">
      <div className={phone ? 'price-toolbar__filters price-toolbar__filters--stack' : 'price-toolbar__filters'}>
        <Segmented label="Фильтр услуг" options={options} value={filter} disabled={disabled} onChange={onFilter} />
      </div>
      <div className="price-toolbar__sort" role="group" aria-label="Сортировка">
        <span className="price-toolbar__label">Сортировка:</span>
        {(['margin', 'profit'] as const).map((key) => (
          <button
            key={key}
            type="button"
            className={sort === key ? 'btn btn--sm price-sort price-sort--on' : 'btn btn--sm price-sort'}
            {...{ 'aria-sort': ariaSort(key) }} // e2e of the tester reads aria-sort here; see frontend/DEVIATIONS.md
            aria-disabled={noRecipes && key === 'margin' ? true : undefined}
            title={noRecipes && key === 'margin' ? 'Сортировать пока нечем' : undefined}
            data-testid={`price-sort-${key}`}
            onClick={() => !(noRecipes && key === 'margin') && onSort(key)}
          >
            {key === 'margin' ? 'Маржа' : 'Прибыль за месяц'}
            {sort === key && <span aria-hidden="true"> {order === 'asc' ? '↑' : '↓'}</span>}
          </button>
        ))}
      </div>
      <input
        type="search"
        className="input price-toolbar__search"
        placeholder="Найти услугу"
        aria-label="Найти услугу"
        autoComplete="off"
        value={search}
        data-testid="price-search"
        onChange={(event) => onSearch(event.target.value)}
      />
    </div>
  )
}

export function PricePage() {
  const params = usePriceParams()
  const { service, filter, sort, order, q, asOf, update } = params
  const query = useServices({ filter, sort, order, q, asOf })
  const toast = useToast()
  const narrow = useMediaQuery(NARROW_LIST_QUERY)
  const [recipe, setRecipe] = useState<RecipeTarget | null>(null)
  const [serviceDialog, setServiceDialog] = useState<ServiceDialogTarget | null>(null)
  const [deleting, setDeleting] = useState<{ id: string; name: string } | null>(null)
  const [focusRecipe, setFocusRecipe] = useState(false)
  const [search, setSearch] = useDebouncedSearch(q, useCallback((next: string) => update({ q: next }, { replace: true }), [update]))
  const { data, error } = query
  const loading = query.isPending
  const slow = useSlowLoading(loading)
  const pages = data?.pages
  const items: ServiceItem[] = useMemo(() => pages?.flatMap((page) => page.items) ?? [], [pages])
  const first = pages?.[0]
  const counts = first?.counts ?? null
  const failedWithoutData = query.isError && !data
  const noRecipes = counts !== null && counts.all > 0 && counts.no_recipe === counts.all
  const [announce, setAnnounce] = useState('')

  const closeCard = useCallback(
    (focusRow = true) => {
      const id = service
      update({ service: null })
      if (focusRow && id) globalThis.setTimeout(() => document.querySelector<HTMLElement>(`[data-row-id="${id}"]`)?.focus(), 0)
    },
    [service, update],
  )
  const cardMissing = useCallback(() => {
    toast.show({ message: 'Эта услуга больше не найдена' })
    update({ service: null }, { replace: true })
  }, [toast, update])

  if (isApiError(error) && error.kind === 'unauthorized') return null

  const openRow = (id: string, row: HTMLElement) => {
    if (id === service) return closeCard()
    const name = row.textContent ?? ''
    setAnnounce(`Открыт разбор: ${name}`)
    update({ service: id })
  }
  const onFilter = (next: FilterId) => {
    update({ filter: next })
    const shown = next === 'all' ? counts?.all : counts?.[next]
    setAnnounce(next === 'all' ? 'Показаны все услуги' : `Показано ${shown ?? 0} ${FILTER_LABELS[next].toLowerCase()}`)
  }
  const onSort = (key: ServiceSort) => update(key === sort ? { order: order === 'asc' ? 'desc' : 'asc' } : { sort: key, order: 'asc' })
  const openRecipe = (id: string, name: string) => setRecipe({ id, name })
  const subtitle = counts ? `${servicesCountText(counts.all)} · разбор позиции до чистой прибыли` : undefined

  return (
    <div data-testid="price" aria-busy={loading || (query.isFetching && Boolean(data))}>
      <PageHeader title="Прайс услуг" subtitle={subtitle} subtitleLoading={loading && !subtitle} balance />
      {loading && (
        <p className="sr-only" role="status">
          Загружаем прайс
        </p>
      )}
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      {slow && <p className="slow-hint">Загрузка идёт дольше обычного. Подождите ещё немного.</p>}
      {data && (
        <DataStrips prefix="price" dataAsOf={undefined} refreshFailed={query.isError && !query.isFetching} onRefresh={() => void query.refetch()} />
      )}
      {loading && <span className="price-skeleton__headline" aria-hidden="true" />}
      {failedWithoutData && (
        <LoadErrorCard
          testId="price-error"
          retryTestId="price-error-retry"
          title="Не получилось загрузить прайс"
          network={isApiError(error) && error.kind === 'network'}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      )}
      {first && counts && counts.all === 0 && !q && filter === 'all' ? (
        <EmptyState
          testId="price-empty"
          icon="🏷️"
          title="Услуг пока нет"
          text="Подключите Ветменеджер: услуги и цены появятся после первой загрузки продаж."
          actions={
            <>
              <Link className="btn" to="/settings/connections/vetmanager">
                Подключения
              </Link>
              <button type="button" className="btn btn--primary" data-testid="price-add" onClick={() => setServiceDialog({ kind: 'new' })}>
                Добавить услугу
              </button>
            </>
          }
        />
      ) : (
        !failedWithoutData && (
          <>
            <Headline data={first} onFill={() => onFilter('no_recipe')} />
            {service && (
              <PriceCard
                key={service}
                id={service}
                asOf={asOf}
                focusRecipe={focusRecipe}
                onFocused={() => setFocusRecipe(false)}
                onClose={() => closeCard()}
                onEditRecipe={(name) => openRecipe(service, name)}
                onEditService={(cost) =>
                  setServiceDialog({
                    kind: 'edit',
                    id: cost.service.id,
                    values: serviceValuesOf(cost.service, cost.price.value),
                    priceKopecks: cost.price.value,
                    priceFromSales: cost.service.price_source === 'sales',
                  })
                }
                onMissing={cardMissing}
              />
            )}
            <section className="price-card" aria-labelledby="price-list-title">
              <div className="price-card__head">
                <h2 id="price-list-title" className="price-card__title">
                  Услуги
                </h2>
                <button type="button" className="btn" data-testid="price-add" onClick={() => setServiceDialog({ kind: 'new' })}>
                  Добавить услугу
                </button>
              </div>
              <Toolbar
                counts={counts}
                filter={filter}
                sort={sort}
                order={order}
                noRecipes={noRecipes}
                search={search}
                disabled={loading}
                onFilter={onFilter}
                onSort={onSort}
                onSearch={setSearch}
              />
              {noRecipes && (
                <p className="price-norecipes" data-testid="price-no-recipes">
                  Техкарт пока нет. Цена и «Оказана» показаны, маржу посчитаем после первой техкарты.
                </p>
              )}
              {loading && <ListSkeleton />}
              {data && items.length > 0 && (
                <div aria-busy={query.isPlaceholderData}>
                  {narrow ? (
                    <PriceCards items={items} selectedId={service} onOpen={openRow} />
                  ) : (
                    <PriceTable items={items} selectedId={service} sort={sort} order={order} onOpen={openRow} />
                  )}
                </div>
              )}
              {data && items.length === 0 && (
                <p className="price-empty-filter" data-testid="price-empty-filter">
                  {q
                    ? 'Ничего не нашли. Проверьте название.'
                    : filter === 'all'
                      ? 'Услуг нет.'
                      : `${FILTER_EMPTY_TEXT[filter].title} ${FILTER_EMPTY_TEXT[filter].text}`.trim()}
                </p>
              )}
              {query.hasNextPage && (
                <div className="price-more">
                  <button type="button" className="btn" disabled={query.isFetchingNextPage} data-testid="price-more" onClick={() => void query.fetchNextPage()}>
                    {query.isFetchingNextPage ? 'Загружаем…' : 'Показать ещё'}
                  </button>
                </div>
              )}
            </section>
          </>
        )
      )}
      {recipe && (
        <RecipeDialog
          target={recipe}
          fallbackFocus={() => document.getElementById('price-list-title')?.focus()}
          onClose={() => setRecipe(null)}
          onSaved={() => {
            setRecipe(null)
            toast.show({ message: 'Техкарта сохранена' })
          }}
        />
      )}
      {serviceDialog && (
        <ServiceDialog
          target={serviceDialog}
          fallbackFocus={() => document.getElementById('price-list-title')?.focus()}
          onClose={() => setServiceDialog(null)}
          onCreated={(item) => {
            setServiceDialog(null)
            toast.show({ message: 'Услуга добавлена' })
            setFocusRecipe(true)
            update({ service: item.id })
          }}
          onSaved={() => {
            setServiceDialog(null)
            toast.show({ message: 'Изменения сохранены' })
          }}
          onDelete={
            serviceDialog.kind === 'edit'
              ? () => setDeleting({ id: serviceDialog.id, name: serviceDialog.values.name })
              : undefined
          }
        />
      )}
      {deleting && (
        <DeleteServiceDialog
          id={deleting.id}
          name={deleting.name}
          onClose={() => setDeleting(null)}
          onMissing={() => {
            setDeleting(null)
            setServiceDialog(null)
            cardMissing()
          }}
          onDeleted={() => {
            setDeleting(null)
            setServiceDialog(null)
            toast.show({ message: 'Услуга удалена' })
            closeCard(false)
          }}
        />
      )}
    </div>
  )
}
