import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from './auth/AuthProvider'
import { IconSprite } from './components/Icon'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { ComingSoonPage, NotFoundPage } from './pages/StubPages'
import { flattenPaths, MENU } from './shell/menu'
import { BrandSplash, Shell } from './shell/Shell'

const SPLASH_SLOW_MS = 3000

function RequireAuth() {
  const { ready, session } = useAuth()
  const location = useLocation()
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    if (ready) return
    const timer = window.setTimeout(() => setSlow(true), SPLASH_SLOW_MS)
    return () => window.clearTimeout(timer)
  }, [ready])

  if (!ready) return <BrandSplash slow={slow} />
  if (!session) {
    const from = location.pathname + location.search
    return <Navigate to="/login" replace state={{ from }} />
  }
  return <Outlet />
}

const SOON_ROUTES = flattenPaths(MENU).filter((item) => item.status !== 'ready' && item.path)

export function App() {
  return (
    <>
      <IconSprite />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Shell />}>
            <Route index element={<DashboardPage />} />
            {SOON_ROUTES.map((item) => (
              <Route key={item.id} path={item.path} element={<ComingSoonPage title={item.label} />} />
            ))}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </>
  )
}
