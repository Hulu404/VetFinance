import type { IconId } from '../components/Icon'

/** ready: opens; soon: shown disabled with a "Скоро" pill; hidden: not shown (design/screens/shell.md). */
export type MenuStatus = 'ready' | 'soon' | 'hidden'

export interface MenuItem {
  id: string
  label: string
  icon?: IconId
  path?: string
  status: MenuStatus
  children?: MenuItem[]
  /** A divider is drawn above the item. */
  dividerBefore?: boolean
}

// Order and names are fixed by design/screens/shell.md. Open a section by changing its status.
export const MENU: MenuItem[] = [
  { id: 'dashboard', label: 'Рабочий стол', icon: 'ic-home', path: '/', status: 'ready' },
  { id: 'transactions', label: 'Транзакции', icon: 'ic-tx', path: '/transactions', status: 'ready' },
  { id: 'price', label: 'Прайс услуг', icon: 'ic-price', path: '/price', status: 'soon' },
  {
    id: 'reports',
    label: 'Отчёты',
    icon: 'ic-report',
    status: 'ready',
    dividerBefore: true,
    children: [
      { id: 'pnl', label: 'Прибыль и убытки', path: '/reports/pnl', status: 'ready' },
      { id: 'norm', label: 'Норма', path: '/reports/norm', status: 'ready' },
      { id: 'stock', label: 'Склад и сроки', path: '/reports/stock', status: 'ready' },
    ],
  },
  {
    id: 'planning',
    label: 'Планирование',
    icon: 'ic-plan',
    status: 'ready',
    children: [
      { id: 'calendar', label: 'Платёжный календарь', path: '/planning/calendar', status: 'ready' },
      { id: 'obligations', label: 'Обязательства', path: '/planning/obligations', status: 'ready' },
    ],
  },
  {
    id: 'analytics',
    label: 'Аналитика',
    icon: 'ic-anal',
    status: 'soon',
    children: [
      { id: 'forecast', label: 'Финмодель и прогноз', path: '/analytics/forecast', status: 'soon' },
      { id: 'efficiency', label: 'Эффективность клиники', path: '/analytics/efficiency', status: 'soon' },
    ],
  },
  { id: 'settings', label: 'Настройки', icon: 'ic-set', path: '/settings', status: 'ready', dividerBefore: true },
]

export function visibleItems(items: MenuItem[]): MenuItem[] {
  return items.filter((item) => item.status !== 'hidden')
}

/** A group is open for navigation when at least one child is ready. */
export function readyChildren(item: MenuItem): MenuItem[] {
  return (item.children ?? []).filter((child) => child.status === 'ready')
}

/** All sections that have a path, for routing placeholders. */
export function flattenPaths(items: MenuItem[]): MenuItem[] {
  return items.flatMap((item) => [...(item.path ? [item] : []), ...flattenPaths(item.children ?? [])])
}
