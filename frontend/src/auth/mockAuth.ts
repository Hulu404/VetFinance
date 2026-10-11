import { AuthError, type AuthClient, type Session } from './types'

const STORAGE_KEY = 'vf-mock-session'
export const MOCK_TOKEN = 'mock-token'
/** In mock mode this password simulates a failed login (used by tests and demos). */
export const MOCK_WRONG_PASSWORD = 'wrong'

function read(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

function write(session: Session | null): void {
  try {
    if (session) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    else window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // storage unavailable: session lives until reload
  }
}

/** Mock login for development without Supabase: any email and password work. */
export function createMockAuth(): AuthClient {
  const listeners = new Set<(session: Session | null) => void>()
  const emit = (session: Session | null) => listeners.forEach((listener) => listener(session))

  return {
    async getSession() {
      return read()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    async signIn(email, password) {
      if (password === MOCK_WRONG_PASSWORD) throw new AuthError('invalid_credentials')
      const session: Session = { email, accessToken: MOCK_TOKEN }
      write(session)
      emit(session)
      return session
    },
    async signOut() {
      write(null)
      emit(null)
    },
  }
}
