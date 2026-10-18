// State and builders of the stage 5 mocks (price list, recipes, efficiency). The base is the golden set 6 of the backend
// (`backend/app/examples/pricing_set06.json`, copied by `npm run sync:mocks`). The mock server plays the part of the backend:
// it may add and compare numbers, the client never does (CLAUDE.md, rule 1). A saved recipe recomputes its card and its row
// in the list; the cost of an hour and the other parts stay those of the example.
import type {
  EfficiencyReport,
  EfficiencySettings,
  Figure,
  PricePart,
  RecipeGroup,
  RecipeItem,
  ServiceCost,
  ServiceItem,
  ServiceList,
  ServiceRecipe,
  StockItem,
} from '../api/types'
import { formatMoney } from '../lib/format'
import { rubFigure } from './figures'
import data from './data/pricing_set06.json'

interface PricingExamples {
  as_of: string
  month: string
  services: ServiceList
  cards: Record<string, ServiceCost>
  card_variants: Record<string, ServiceCost>
  recipes: Record<string, ServiceRecipe>
  stock_items: { items: StockItem[]; next_cursor: string | null }
  efficiency: Record<string, EfficiencyReport>
  efficiency_settings: EfficiencySettings
}

const examples = data as unknown as PricingExamples

export const pricingAsOf = examples.as_of
export const pricingMonth = examples.month
export const efficiencyExamples = examples.efficiency
export const cardVariants = examples.card_variants

export const GROUPS: RecipeGroup[] = ['drugs', 'anesthesia', 'supplies']
const GROUP_PARTS: Record<RecipeGroup, 'drugs' | 'anesthesia' | 'supplies'> = {
  drugs: 'drugs',
  anesthesia: 'anesthesia',
  supplies: 'supplies',
}
const PART_LABELS: Record<string, string> = { drugs: 'Препараты', anesthesia: 'Анестезия', supplies: 'Расходники' }

interface PricingState {
  services: ServiceItem[]
  cards: Record<string, ServiceCost>
  recipes: Record<string, ServiceRecipe>
  settings: EfficiencySettings
  /** The hours of doctors were saved in this session: the scenarios "no hours" then show the computed answer. */
  hoursSaved: boolean
  nextId: number
}

function freshState(): PricingState {
  return {
    services: structuredClone(examples.services.items),
    cards: structuredClone(examples.cards),
    recipes: structuredClone(examples.recipes),
    settings: structuredClone(examples.efficiency_settings),
    hoursSaved: false,
    nextId: 1,
  }
}

export const pricing: PricingState = freshState()

/** Test helper: back to the example. */
export function resetPricing(): void {
  Object.assign(pricing, freshState())
}

export function newServiceId(): string {
  const id = `manual-service-${pricing.nextId}`
  pricing.nextId += 1
  return id
}

/** All warehouse items the mock knows: the first page of the example and the items of the recipes. */
export function stockCatalog(): StockItem[] {
  const byId = new Map<string, StockItem>()
  for (const item of examples.stock_items.items) byId.set(item.id, item)
  for (const recipe of Object.values(examples.recipes)) {
    for (const item of recipe.items) {
      if (!byId.has(item.item_id)) byId.set(item.item_id, { id: item.item_id, name: item.name, unit: item.unit, unit_cost: item.unit_cost })
    }
  }
  return [...byId.values()]
}

export function normalizeName(text: string): string {
  return text.trim().replace(/\s+/g, ' ').toLowerCase().replaceAll('ё', 'е')
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod100 = n % 100
  const mod10 = n % 10
  if (mod100 >= 11 && mod100 <= 14) return many
  if (mod10 === 1) return one
  if (mod10 >= 2 && mod10 <= 4) return few
  return many
}

/** The sentence of the list, by the template of the contract. */
export function buildHeadline(items: ServiceItem[]): string | undefined {
  if (items.length === 0) return undefined
  const withMargin = items.filter((item) => item.margin_pct !== null).sort((a, b) => (a.margin_pct?.value ?? 0) - (b.margin_pct?.value ?? 0))
  const noRecipe = items.length - withMargin.length
  if (withMargin.length === 0) {
    return 'Техкарт пока нет, поэтому маржу мы не считаем. Начните с самых частых услуг: для каждой нужен список материалов и время.'
  }
  const worst = withMargin[0]
  const losses = withMargin.filter((item) => (item.margin_pct?.value ?? 0) < 0).length
  const pct = (value: number) => `${value < 0 ? '−' : ''}${Math.abs(value).toFixed(1).replace('.', ',')}%`
  const head =
    losses > 0 && worst?.margin_pct
      ? `${losses} ${plural(losses, 'услуга', 'услуги', 'услуг')} из ${items.length} ${plural(losses, 'стоит', 'стоят', 'стоят')} клинике больше, чем ${plural(losses, 'приносит', 'приносят', 'приносят')}. Сильнее всего «${worst.name}»: ${pct(worst.margin_pct.value)}.`
      : `Все услуги с техкартой приносят прибыль. Меньше всего у «${worst?.name ?? ''}»: ${pct(worst?.margin_pct?.value ?? 0)}.`
  if (noRecipe === 0) return head
  return `${head} У ${noRecipe} ${plural(noRecipe, 'услуги', 'услуг', 'услуг')} нет техкарты, поэтому их маржу мы не считаем.`
}

const countFig = (value: number, label: string, note: string): Figure => ({
  value,
  unit: 'count',
  breakdown: [{ label, value, unit: 'count' }],
  source: ['vetmanager'],
  note,
})

/** The row of a new manual service. */
export function manualRow(id: string, name: string, group: string | null, price: number): ServiceItem {
  return {
    id,
    name,
    group,
    unit_label: 'раз',
    source: 'manual',
    price: rubFigure(price, [['Цена, введённая вручную', price]], ['manual'], 'Продаж по услуге за 90 дней нет.'),
    visits_month: countFig(0, 'Оказана за прошлый месяц', 'Услуга не оказывалась.'),
    margin_pct: null,
    monthly_profit: null,
    status: 'no_recipe',
  }
}

const NO_RECIPE_TEMPLATE_ID = '71293917-975f-5e89-9069-0ff8bcc42a69'

/** The card of a service without a recipe: the known parts are those of the template scaled to the price. */
export function noRecipeCard(item: ServiceItem): ServiceCost {
  const template = examples.cards[NO_RECIPE_TEMPLATE_ID] as ServiceCost
  const base = template.price.value
  const price = item.price.value
  const parts: PricePart[] = template.parts.map((part) => {
    if (part.amount === null || part.share_pct === null) return part
    const amount = Math.round((part.amount.value * price) / base)
    return { ...part, amount: { ...part.amount, value: amount, breakdown: [{ label: part.label, value: amount, unit: 'rub' }] } }
  })
  return {
    ...template,
    service: { id: item.id, name: item.name, group: item.group, unit_label: item.unit_label, source: item.source, price_source: item.source === 'manual' ? 'manual' : 'sales' },
    price: { ...item.price, note: 'Разложить цену на части нельзя, пока нет техкарты: без материалов прибыль была бы завышена.' },
    parts,
    visits_month: item.visits_month,
  }
}

export function cardFor(id: string): ServiceCost | null {
  const stored = pricing.cards[id]
  if (stored) return stored
  const row = pricing.services.find((item) => item.id === id)
  return row ? noRecipeCard(row) : null
}

function hourCostOf(card: ServiceCost): number | null {
  const fixed = card.parts.find((part) => part.key === 'fixed')?.amount
  const details = fixed?.details?.find((detail) => detail.label === 'Стоимость часа')
  return details ? details.value : null
}

function recipeLines(items: RecipeItem[], group: RecipeGroup): { lines: [string, number][]; missing: string[] } {
  const lines: [string, number][] = []
  const missing: string[] = []
  for (const item of items.filter((candidate) => candidate.group === group)) {
    if (item.unit_cost === null) {
      missing.push(item.name)
      continue
    }
    const amount = Math.round(item.qty * item.unit_cost.value)
    lines.push([`${item.name}, ${String(item.qty).replace('.', ',')} ${item.unit} × ${formatMoney(item.unit_cost.value)}`, amount])
  }
  return { lines, missing }
}

function materialPart(key: PricePart['key'], recipe: ServiceRecipe, group: RecipeGroup): { part: PricePart; missing: string[] } {
  const { lines, missing } = recipeLines(recipe.items, group)
  const total = lines.reduce((sum, [, amount]) => sum + amount, 0)
  const amount: Figure = {
    ...rubFigure(
      total,
      lines,
      ['manual', 'vetmanager'],
      'Количество из техкарты × закупочная цена со склада. Если на складе несколько партий, берём среднюю по остатку.',
    ),
    details: missing.map((name) => ({ label: `Нет цены закупки: ${name}`, value: 0, unit: 'rub' as const })),
  }
  if (lines.length === 0) amount.breakdown = [{ label: PART_LABELS[key] ?? key, value: 0, unit: 'rub' }]
  return { part: { key, label: PART_LABELS[key] ?? key, amount, share_pct: null }, missing }
}

function shareFigure(amount: number, price: number, share: number, label: string): Figure {
  const text = (value: number) => formatMoney(value).replace(/\s₽$/, '')
  return {
    value: share,
    unit: 'pct',
    breakdown: [
      { label: 'Сумма части', value: amount, unit: 'rub' },
      { label: 'Цена', value: price, unit: 'rub' },
    ],
    source: ['calc'],
    note: `${text(amount)} ÷ ${text(price)} (${label})`,
  }
}

function withShares(parts: PricePart[], price: number): { parts: PricePart[]; netShare: number } {
  let rest = 1000
  const next = parts.map((part) => {
    const amount = part.amount?.value ?? 0
    const tenths = Math.round((amount / price) * 1000)
    rest -= tenths
    const share = part.amount ? shareFigure(amount, price, tenths / 10, part.label) : null
    return { ...part, share_pct: share }
  })
  return { parts: next, netShare: rest / 10 }
}

/** Recomputes the card after a recipe was saved. Only what the recipe changes: materials, own percent and minutes. */
export function applyRecipe(card: ServiceCost, recipe: ServiceRecipe): ServiceCost {
  const price = card.price.value
  const hourCost = hourCostOf(card)
  const built = (['drugs', 'anesthesia', 'supplies'] as const).map((key) => materialPart(key, recipe, GROUP_PARTS[key]))
  const missing = built.flatMap((entry) => entry.missing)
  const parts = card.parts.map((part) => {
    const material = built.find((entry) => entry.part.key === part.key)
    if (material) return material.part
    if (part.key === 'doctor_pay' && recipe.doctor_pct !== null) {
      const amount = Math.round((price * recipe.doctor_pct) / 100)
      return {
        ...part,
        amount: {
          ...rubFigure(amount, [['Процент врачу от цены', amount]], ['manual', 'calc'], `${formatMoney(price)} × ${String(recipe.doctor_pct).replace('.', ',')}%. Процент задан для этой услуги.`),
          details: [{ label: 'Процент', value: recipe.doctor_pct, unit: 'pct' as const }],
        },
      }
    }
    if (part.key === 'fixed' && hourCost !== null && recipe.minutes !== null) {
      const amount = Math.round((hourCost * recipe.minutes) / 60)
      return { ...part, amount: { ...part.amount, ...rubFigure(amount, [['Время в кабинете', amount]], ['calc', 'manual'], `${formatMoney(hourCost)} × ${recipe.minutes} ÷ 60.`) } }
    }
    return part
  })
  const known = parts.reduce((sum, part) => sum + (part.amount?.value ?? 0), 0)
  const net = price - known
  const shared = withShares(parts, price)
  const visits = card.visits_month.value
  const margin: Figure = {
    value: shared.netShare,
    unit: 'pct',
    breakdown: [
      { label: 'Чистая прибыль', value: net, unit: 'rub' },
      { label: 'Цена', value: price, unit: 'rub' },
    ],
    source: ['calc'],
    note: `${formatMoney(net)} ÷ ${formatMoney(price)}`,
  }
  const profit = rubFigure(net, [['Цена', price], ...shared.parts.flatMap((part): [string, number][] => (part.amount ? [[part.label, -part.amount.value]] : []))], ['calc'], net < 0 ? `Услуга работает в минус: не хватает ${formatMoney(Math.abs(net))} на одну услугу до нуля.` : 'Столько остаётся с одной услуги после всех расходов и налогов.')
  const monthly = rubFigure(net * visits, [['Чистая прибыль одной услуги × оказана', net * visits]], ['calc'], `${formatMoney(net)} × ${visits}`)
  return {
    ...card,
    status: missing.length > 0 ? 'partial' : 'ok',
    missing: missing.length > 0 ? ['item_no_cost'] : [],
    minutes: recipe.minutes ?? card.minutes,
    minutes_source: recipe.minutes === null ? 'clinic_average' : 'own',
    price: {
      ...card.price,
      breakdown: [...shared.parts.flatMap((part) => (part.amount && part.amount.value !== 0 ? [{ label: part.label, value: part.amount.value, unit: 'rub' as const }] : [])), { label: 'Чистая прибыль', value: net, unit: 'rub' as const }],
      note: `Части и чистая прибыль вместе дают цену ${formatMoney(price)}.`,
    },
    net_profit: profit,
    net_margin_pct: margin,
    parts: shared.parts,
    monthly_profit: monthly,
  }
}

/** The row of the list after the card changed. */
export function rowFromCard(row: ServiceItem, card: ServiceCost): ServiceItem {
  return { ...row, status: card.status, margin_pct: card.net_margin_pct, monthly_profit: card.monthly_profit }
}
