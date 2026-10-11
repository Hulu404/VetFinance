export interface Session {
  email: string
  accessToken: string
}

export type AuthErrorKind = 'invalid_credentials' | 'rate_limited' | 'network' | 'other'

export class AuthError extends Error {
  readonly kind: AuthErrorKind
  constructor(kind: AuthErrorKind) {
    super(kind)
    this.name = 'AuthError'
    this.kind = kind
  }
}

export interface AuthClient {
  getSession(): Promise<Session | null>
  /** Calls back on sign-in, sign-out and token refresh. Returns unsubscribe. */
  subscribe(listener: (session: Session | null) => void): () => void
  signIn(email: string, password: string): Promise<Session>
  signOut(): Promise<void>
}
