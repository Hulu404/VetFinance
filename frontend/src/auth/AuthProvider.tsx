import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { setTokenProvider, setUnauthorizedHandler } from '../api/client'
import { isMockMode } from '../lib/config'
import { createMockAuth } from './mockAuth'
import { createSupabaseAuth } from './supabaseAuth'
import { AuthError, type AuthClient, type Session } from './types'

interface AuthState {
  /** false while the stored session is being checked */
  ready: boolean
  session: Session | null
  /** true after the API answered 401 (shown on the login screen) */
  expired: boolean
  signIn(email: string, password: string): Promise<void>
  signOut(): Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

function createAuthClient(): AuthClient {
  return isMockMode() ? createMockAuth() : createSupabaseAuth()
}

export function AuthProvider({ children, client }: { children: ReactNode; client?: AuthClient }) {
  const queryClient = useQueryClient()
  const authRef = useRef<AuthClient | null>(client ?? null)
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const [expired, setExpired] = useState(false)
  const [configError, setConfigError] = useState(false)
  const sessionRef = useRef<Session | null>(null)

  const applySession = useCallback(
    (next: Session | null) => {
      sessionRef.current = next
      setSession(next)
      if (!next) queryClient.clear()
    },
    [queryClient],
  )

  useEffect(() => {
    let active = true
    let unsubscribe: () => void = () => undefined
    try {
      authRef.current ??= createAuthClient()
    } catch {
      setConfigError(true)
      setReady(true)
      return
    }
    const auth = authRef.current
    setTokenProvider(async () => sessionRef.current?.accessToken ?? (await auth.getSession())?.accessToken ?? null)
    unsubscribe = auth.subscribe((next) => active && applySession(next))
    auth
      .getSession()
      .then((stored) => active && applySession(stored))
      .catch(() => active && applySession(null))
      .finally(() => active && setReady(true))
    return () => {
      active = false
      unsubscribe()
    }
  }, [applySession])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setExpired(true)
      void authRef.current?.signOut()
    })
  }, [])

  const signIn = useCallback(
    async (email: string, password: string) => {
      if (!authRef.current || configError) throw new AuthError('other')
      setExpired(false)
      const next = await authRef.current.signIn(email, password)
      applySession(next)
    },
    [applySession, configError],
  )

  const signOut = useCallback(async () => {
    setExpired(false)
    await authRef.current?.signOut()
    applySession(null)
  }, [applySession])

  const value = useMemo<AuthState>(
    () => ({ ready, session, expired, signIn, signOut }),
    [ready, session, expired, signIn, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
