import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useClinic } from '../api/queries'
import { useAuth } from '../auth/AuthProvider'
import { Icon } from '../components/Icon'
import { Pill } from '../components/Pill'
import { MENU, readyChildren, visibleItems, type MenuItem } from './menu'
import './Sidebar.css'

function BrandBlock() {
  const clinic = useClinic()
  const name = clinic.data?.name
  return (
    <div className="brand">
      <div className="brand__mark" aria-hidden="true">
        <Icon id="ic-logo" />
      </div>
      <div className="brand__text">
        <span className="brand__name">ВетФинанс</span>
        {clinic.isPending ? (
          <span className="brand__skeleton" aria-hidden="true" />
        ) : name ? (
          <span className="brand__clinic" title={name}>
            {name}
          </span>
        ) : null}
      </div>
    </div>
  )
}

function SoonItem({ item }: { item: MenuItem }) {
  return (
    <button type="button" className="nav__item nav__item--soon" disabled>
      {item.icon && <Icon id={item.icon} />}
      <span className="nav__text">{item.label}</span>
      <Pill variant="on-dark">Скоро</Pill>
    </button>
  )
}

function ReadyLink({ item, sub = false }: { item: MenuItem; sub?: boolean }) {
  return (
    <NavLink to={item.path ?? '/'} end={item.path === '/'} className={sub ? 'nav__sub-item' : 'nav__item'}>
      {item.icon && <Icon id={item.icon} />}
      <span className="nav__text">{item.label}</span>
    </NavLink>
  )
}

function Group({ item }: { item: MenuItem }) {
  const location = useLocation()
  const children = readyChildren(item)
  const active = children.some((child) => child.path && location.pathname.startsWith(child.path))
  const [expanded, setExpanded] = useState(active)
  const open = expanded || active
  return (
    <div className="nav__group">
      <button
        type="button"
        className="nav__item"
        aria-expanded={open}
        onClick={() => setExpanded((value) => !value)}
      >
        {item.icon && <Icon id={item.icon} />}
        <span className="nav__text">{item.label}</span>
        <span className={open ? 'nav__chevron nav__chevron--open' : 'nav__chevron'} aria-hidden="true">
          ▸
        </span>
      </button>
      {open && (
        <div className="nav__sub">
          {children.map((child) => (
            <ReadyLink key={child.id} item={child} sub />
          ))}
        </div>
      )}
    </div>
  )
}

function NavEntry({ item }: { item: MenuItem }) {
  const hasChildren = Boolean(item.children?.length)
  let entry
  if (hasChildren) {
    entry = readyChildren(item).length > 0 ? <Group item={item} /> : <SoonItem item={item} />
  } else {
    entry = item.status === 'ready' ? <ReadyLink item={item} /> : <SoonItem item={item} />
  }
  return (
    <>
      {item.dividerBefore && <hr className="nav__divider" />}
      {entry}
    </>
  )
}

export function Sidebar() {
  const { session, signOut } = useAuth()
  const email = session?.email ?? ''
  const initial = email.charAt(0).toUpperCase()

  return (
    <aside className="sidebar on-dark">
      <BrandBlock />
      <nav aria-label="Основное меню" className="nav">
        {visibleItems(MENU).map((item) => (
          <NavEntry key={item.id} item={item} />
        ))}
      </nav>
      <div className="sfoot">
        <span className="sfoot__avatar" aria-hidden="true">
          {initial}
        </span>
        <span className="sfoot__email" title={email}>
          {email}
        </span>
        <button type="button" className="sfoot__logout" onClick={() => void signOut()}>
          Выйти
        </button>
      </div>
    </aside>
  )
}
