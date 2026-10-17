import { useEffect, useState, type FormEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { usePatchClinic } from '../../api/mutations'
import { useClinic } from '../../api/queries'
import { Field } from '../../components/Field'
import { InlineAlert, LoadErrorCard } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { formatAmountInput, parseAmount, type AmountError } from '../../lib/money'

const SAFE_ANCHOR = 'safe-balance'
const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'
const NEGATIVE_TEXT = 'Запас не может быть меньше нуля'

const AMOUNT_TEXT: Record<AmountError, string> = {
  empty: '',
  not_number: 'Введите сумму цифрами, например 60 000',
  zero: '',
  decimals: 'Не больше двух знаков после запятой',
  too_large: 'Слишком большая сумма',
}

const SERVER_CODE_TEXT: Record<string, string> = {
  invalid: AMOUNT_TEXT.not_number,
  must_be_positive: NEGATIVE_TEXT,
  too_many_decimals: AMOUNT_TEXT.decimals,
  too_large: AMOUNT_TEXT.too_large,
}

export type SafeBalanceParse = { ok: true; kopecks: number } | { ok: false; error: string }

/** The safe balance in rubles as typed. Empty is 0 ("not set"); a minus sign is the "can't be less than zero" mistake. */
export function parseSafeBalance(input: string): SafeBalanceParse {
  const text = input.trim()
  if (text === '') return { ok: true, kopecks: 0 }
  if (/^[-−]\s*\d/.test(text)) return { ok: false, error: NEGATIVE_TEXT }
  const parsed = parseAmount(text, { allowZero: true })
  return parsed.ok ? parsed : { ok: false, error: AMOUNT_TEXT[parsed.error] }
}

function SafeBalanceCard({ saved }: { saved: number }) {
  const patch = usePatchClinic()
  const toast = useToast()
  const [value, setValue] = useState(saved === 0 ? '' : formatAmountInput(saved))
  const [error, setError] = useState<string | null>(null)
  const [general, setGeneral] = useState<string | null>(null)
  const busy = patch.isPending

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const parsed = parseSafeBalance(value)
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }
    setError(null)
    // mutateAsync, not mutate callbacks: the saved value re-keys this card, and callbacks of an unmounted card never run.
    patch.mutateAsync({ safe_balance: parsed.kopecks }).then(
      () => toast.show({ message: 'Запас сохранён' }),
      (cause: unknown) => {
        if (isApiError(cause) && cause.kind === 'validation') {
          const code = cause.fields.safe_balance
          if (code) return setError(SERVER_CODE_TEXT[code] ?? 'Проверьте значение')
        }
        setGeneral(SERVER_TEXT)
      },
    )
  }

  return (
    <section id={SAFE_ANCHOR} className="set-card" aria-labelledby="safe-title" data-testid="settings-safe-balance">
      <h2 id="safe-title" className="klabel">
        Безопасный запас на счетах
      </h2>
      <form className="set-form" noValidate onSubmit={submit}>
        {general && <InlineAlert testId="settings-safe-balance-general">{general}</InlineAlert>}
        <Field
          label="Предупреждать, если остаток ниже"
          error={error}
          errorTestId="settings-safe-balance-error"
          hint="Если остаток упадёт ниже этой суммы, дни в платёжном календаре отметятся красным и подписью «ниже запаса». Оставьте пустым, если запас не нужен."
        >
          {(control) => (
            <div className="amount">
              <input
                {...control}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                className="input"
                placeholder="0"
                data-testid="settings-safe-balance-input"
                value={value}
                disabled={busy}
                onChange={(event) => {
                  setValue(event.target.value)
                  setError(null)
                }}
              />
              <span className="amount__unit" aria-hidden="true">
                ₽
              </span>
            </div>
          )}
        </Field>
        <div className="set-actions">
          <button type="submit" className="btn btn--primary" disabled={busy} aria-busy={busy || undefined} data-testid="settings-safe-balance-save">
            {busy ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </div>
      </form>
    </section>
  )
}

/** Settings -> Основное. On stage 4 only the safe balance can be changed; the rest of the clinic card is read-only for now. */
export function MainSection() {
  const clinic = useClinic()
  const location = useLocation()

  // A link from the calendar ends in #safe-balance: the card is brought into view once it is drawn.
  useEffect(() => {
    if (location.hash !== `#${SAFE_ANCHOR}` || !clinic.data) return
    document.getElementById(SAFE_ANCHOR)?.scrollIntoView?.({ block: 'start' })
  }, [location.hash, clinic.data])

  if (clinic.isPending) {
    return (
      <section className="set-card" aria-busy="true" aria-label="Основное">
        <p className="sr-only" role="status">
          Загружаем настройки
        </p>
        <div className="set-skel" aria-hidden="true" />
      </section>
    )
  }
  if (!clinic.data) {
    return (
      <LoadErrorCard
        testId="settings-main-error"
        title="Не получилось загрузить настройки"
        network={isApiError(clinic.error) && clinic.error.kind === 'network'}
        retrying={clinic.isFetching}
        onRetry={() => void clinic.refetch()}
      />
    )
  }
  const data = clinic.data
  return (
    <>
      <section className="set-card" aria-labelledby="clinic-title" data-testid="settings-clinic">
        <h2 id="clinic-title" className="klabel">
          Клиника
        </h2>
        <div className="set-line set-line--static">
          <span className="fld__label">Название</span>
          <span className="set-static">{data.name}</span>
        </div>
        <div className="set-line set-line--static">
          <span className="fld__label">Юридическое лицо</span>
          <span className="set-static">{data.legal_entity ?? 'не указано'}</span>
        </div>
        <div className="set-line set-line--static">
          <span className="fld__label">Налоговый режим</span>
          <span className="set-static">{data.tax_regime ?? 'не указан'}</span>
        </div>
        <div className="set-line set-line--static">
          <span className="fld__label">Часовой пояс</span>
          <span className="set-static">{data.timezone}</span>
        </div>
      </section>
      <div className="set-gap" />
      <SafeBalanceCard key={data.safe_balance} saved={data.safe_balance} />
    </>
  )
}
