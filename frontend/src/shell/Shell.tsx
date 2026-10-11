import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useClinic } from '../api/queries'
import { isApiError } from '../api/errors'
import { useAuth } from '../auth/AuthProvider'
import { Icon } from '../components/Icon'
import { useOnline } from '../lib/useOnline'
import { Sidebar } from './Sidebar'
import './Shell.css'

export function BrandSplash({ slow = false }: { slow?: boolean }) {
  return (
    <div className="splash" role="status">
      <div className="splash__mark" aria-hidden="true">
        <Icon id="ic-logo" />
      </div>
      {slow && <p className="splash__text">Проверяем вход…</p>}
    </div>
  )
}

function NoClinic() {
  const { signOut } = useAuth()
  return (
    <main className="center-screen" id="content">
      <div className="center-card">
        <h1 className="center-card__title">Ваша почта пока не привязана к клинике</h1>
        <p className="center-card__text">Напишите нам, мы подключим.</p>
        <button type="button" className="btn btn--primary" onClick={() => void signOut()}>
          Выйти
        </button>
      </div>
    </main>
  )
}

export function Shell() {
  const clinic = useClinic()
  const online = useOnline()
  const location = useLocation()
  const firstRender = useRef(true)

  // After a page change, focus moves to the page heading so keyboard and screen reader users start there.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    window.scrollTo(0, 0)
    document.querySelector<HTMLElement>('main h1')?.focus()
  }, [location.pathname])

  if (isApiError(clinic.error) && (clinic.error.kind === 'forbidden' || clinic.error.kind === 'not_found')) {
    return <NoClinic />
  }

  return (
    <div className="app">
      <a className="skip-link" href="#content">
        Перейти к содержимому
      </a>
      <Sidebar />
      <main id="content" tabIndex={-1} className="main">
        {!online && (
          <p className="offline-bar" role="status">
            Нет связи с сервером. Показаны последние загруженные данные.
          </p>
        )}
        <div className="view">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
