import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { AuthError } from '../auth/types'
import { Icon } from '../components/Icon'
import { usePageTitle } from '../lib/usePageTitle'
import './LoginPage.css'

const MESSAGES = {
  invalid_credentials: 'Неверная почта или пароль. Проверьте и попробуйте ещё раз.',
  rate_limited: 'Слишком много попыток. Подождите минуту и попробуйте снова.',
  network: 'Нет связи с сервером. Проверьте интернет и повторите.',
  other: 'Не получилось войти. Попробуйте ещё раз через минуту.',
} as const

interface FieldErrors {
  email?: string
  password?: string
}

function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!email.trim()) errors.email = 'Введите почту'
  else if (!email.includes('@')) errors.email = 'Проверьте почту: похоже, в адресе опечатка'
  if (!password) errors.password = 'Введите пароль'
  return errors
}

interface LocationState {
  from?: string
}

export function LoginPage() {
  usePageTitle('Вход')
  const { session, ready, expired, signIn } = useAuth()
  const location = useLocation()
  const target = (location.state as LocationState | null)?.from ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    emailRef.current?.focus()
  }, [])

  if (ready && session) return <Navigate to={target} replace />

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting) return
    const found = validate(email, password)
    setErrors(found)
    setFormError(null)
    if (found.email) {
      emailRef.current?.focus()
      return
    }
    if (found.password) {
      passwordRef.current?.focus()
      return
    }
    setSubmitting(true)
    try {
      await signIn(email.trim(), password)
    } catch (error) {
      const kind = error instanceof AuthError ? error.kind : 'other'
      setFormError(MESSAGES[kind])
      if (kind === 'invalid_credentials') {
        setPassword('')
        window.setTimeout(() => passwordRef.current?.focus(), 0)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login" id="content">
      <div className="login__brand">
        <span className="login__mark" aria-hidden="true">
          <Icon id="ic-logo" />
        </span>
        <span className="login__name">ВетФинанс</span>
      </div>
      <div className="login__card">
        <h1>Вход</h1>
        <p className="login__lead">Войдите, чтобы увидеть деньги клиники</p>
        {expired && !formError && (
          <p className="login__notice" role="status">
            Сессия закончилась. Войдите снова.
          </p>
        )}
        <form onSubmit={(event) => void handleSubmit(event)} noValidate>
          <div className="field">
            <label htmlFor="login-email">Почта</label>
            <input
              id="login-email"
              ref={emailRef}
              className="input"
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={email}
              disabled={submitting}
              aria-invalid={errors.email ? true : undefined}
              aria-describedby={errors.email ? 'login-email-error' : undefined}
              onChange={(event) => {
                setEmail(event.target.value)
                setErrors((previous) => ({ ...previous, email: undefined }))
                setFormError(null)
              }}
            />
            {errors.email && (
              <p id="login-email-error" className="field__error">
                {errors.email}
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor="login-password">Пароль</label>
            <input
              id="login-password"
              ref={passwordRef}
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={submitting}
              aria-invalid={errors.password ? true : undefined}
              aria-describedby={errors.password ? 'login-password-error' : undefined}
              onChange={(event) => {
                setPassword(event.target.value)
                setErrors((previous) => ({ ...previous, password: undefined }))
                setFormError(null)
              }}
            />
            {errors.password && (
              <p id="login-password-error" className="field__error">
                {errors.password}
              </p>
            )}
          </div>
          {formError && (
            <p className="login__error" role="alert">
              {formError}
            </p>
          )}
          <button type="submit" className="btn btn--primary btn--block" disabled={submitting} aria-busy={submitting}>
            {submitting ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </div>
      <p className="login__note">Нет доступа? Его выдаёт команда ВетФинанс.</p>
    </main>
  )
}
