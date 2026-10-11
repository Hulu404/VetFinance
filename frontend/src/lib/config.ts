// Runtime configuration. Read lazily so tests can stub env.
export function getApiUrl(): string {
  return (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/+$/, '')
}

/** Mock mode: no VITE_API_URL. API is served by MSW, login accepts any credentials. */
export function isMockMode(): boolean {
  return getApiUrl() === ''
}

export function getSupabaseConfig(): { url: string; anonKey: string } | null {
  const url = (import.meta.env.VITE_SUPABASE_URL ?? '').trim()
  const anonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY ?? '').trim()
  return url && anonKey ? { url, anonKey } : null
}
