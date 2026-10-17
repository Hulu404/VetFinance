import { useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { Pill } from '../../components/Pill'
import './SettingsPage.css'

interface SettingsItem {
  label: string
  /** Absent for sections that are not built yet ("Скоро"). */
  path?: string
}

interface SettingsGroup {
  title: string
  items: SettingsItem[]
}

// Groups and items follow design/screens/connections.md, "Внутреннее меню" (no users, no bot).
const GROUPS: SettingsGroup[] = [
  { title: 'Клиника', items: [{ label: 'Основное', path: '/settings/main' }, { label: 'Счета' }] },
  { title: 'Справочники', items: [{ label: 'Категории' }, { label: 'Направления' }] },
  {
    title: 'Подключения',
    items: [
      { label: 'Ветменеджер', path: '/settings/connections/vetmanager' },
      { label: 'Банк', path: '/settings/connections/bank' },
    ],
  },
  { title: 'Прочее', items: [{ label: 'Журнал действий' }, { label: 'Подписка' }] },
]

function SettingsNav() {
  const location = useLocation()
  const navRef = useRef<HTMLElement | null>(null)

  // On a narrow screen the menu is a strip: the chosen item is brought into view.
  useEffect(() => {
    const current = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]')
    current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [location.pathname])

  return (
    <nav className="setnav" aria-label="Разделы настроек" ref={navRef}>
      {GROUPS.map((group) => (
        <div key={group.title} className="setnav__group">
          <p className="setnav__title">{group.title}</p>
          {group.items.map((item) =>
            item.path ? (
              <NavLink key={item.label} to={item.path} className="setnav__item">
                {item.label}
              </NavLink>
            ) : (
              <button key={item.label} type="button" className="setnav__item setnav__item--soon" disabled>
                {item.label}
                <Pill variant="neutral">Скоро</Pill>
              </button>
            ),
          )}
        </div>
      ))}
    </nav>
  )
}

export function SettingsLayout() {
  return (
    <>
      <PageHeader title="Настройки" subtitle="Клиника, справочники и подключения" balance />
      <div className="settings">
        <SettingsNav />
        <div className="settings__content">
          <Outlet />
        </div>
      </div>
    </>
  )
}

/** Opened by typing the address of a settings section that is not built yet. */
export function SettingsSoon() {
  return (
    <section className="set-card" aria-label="Раздел пока недоступен">
      <p className="set-text">Этот раздел откроем позже.</p>
    </section>
  )
}
