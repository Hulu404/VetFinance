import { createClient, type Session as SupabaseSession } from '@supabase/supabase-js'
import { getSupabaseConfig } from '../lib/config'
import { AuthError, type AuthClient, type Session } from './types'

function toSession(session: SupabaseSession | null): Session | null {
  if (!session) return null
  return { email: session.user.email ?? '', accessToken: session.access_token }
}

function toAuthError(error: { status?: number; code?: string; name?: string }): AuthError {
  if (error.status === 429 || error.code === 'over_request_rate_limit') return new AuthError('rate_limited')
  if (error.code === 'invalid_credentials' || error.status === 400) return new AuthError('invalid_credentials')
  if (error.name === 'AuthRetryableFetchError' || error.status === 0) return new AuthError('network')
  return new AuthError('other')
}

/** Supabase Auth (email + password). The Supabase client keeps the session itself. */
export function createSupabaseAuth(): AuthClient {
  const config = getSupabaseConfig()
  if (!config) throw new AuthError('other')
  const supabase = createClient(config.url, config.anonKey)

  return {
    async getSession() {
      const { data } = await supabase.auth.getSession()
      return toSession(data.session)
    },
    subscribe(listener) {
      const { data } = supabase.auth.onAuthStateChange((_event, session) => listener(toSession(session)))
      return () => data.subscription.unsubscribe()
    },
    async signIn(email, password) {
      let result
      try {
        result = await supabase.auth.signInWithPassword({ email, password })
      } catch {
        throw new AuthError('network')
      }
      if (result.error) throw toAuthError(result.error)
      const session = toSession(result.data.session)
      if (!session) throw new AuthError('other')
      return session
    },
    async signOut() {
      await supabase.auth.signOut()
    },
  }
}
