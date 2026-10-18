import { useMemo, useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useSaveEfficiencySettings } from '../../api/mutations'
import { useEfficiencySettings } from '../../api/queries'
import type { EfficiencySettings } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { Field, type FieldControlProps } from '../../components/Field'
import { InlineAlert } from '../../components/StateBlocks'
import { checkHoursForm, doctorKey, initialHours, serverError, type HoursErrors, type HoursValues } from './hoursForm'

const NETWORK_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите'
const SERVER_TEXT = 'Не получилось сохранить. Попробуйте ещё раз.'
const TITLE = 'Часы приёма'
const SUBTITLE = 'Сколько часов в неделю принимает каждый врач. По ним считаем загрузку и стоимость часа.'

interface HoursDialogProps {
  fallbackFocus?: () => void
  onClose: () => void
  onSaved: () => void
}

/** Opens at once; the form appears when the settings have come. */
export function HoursDialog({ fallbackFocus, onClose, onSaved }: HoursDialogProps) {
  const settings = useEfficiencySettings()
  if (settings.data) return <HoursForm settings={settings.data} fallbackFocus={fallbackFocus} onClose={onClose} onSaved={onSaved} />
  return (
    <Dialog title={TITLE} subtitle={SUBTITLE} onClose={onClose} fallbackFocus={fallbackFocus} testId="efficiency-hours-dialog">
      {settings.isError ? (
        <InlineAlert testId="efficiency-hours-load-error">
          {isApiError(settings.error) && settings.error.kind === 'network' ? NETWORK_TEXT : 'Не получилось загрузить настройки.'}{' '}
          <button type="button" className="btn btn--text" onClick={() => void settings.refetch()}>
            Повторить
          </button>
        </InlineAlert>
      ) : (
        <p role="status">Загружаем настройки…</p>
      )}
    </Dialog>
  )
}

interface FormProps extends HoursDialogProps {
  settings: EfficiencySettings
}

function HoursForm({ settings, fallbackFocus, onClose, onSaved }: FormProps) {
  const initial = useMemo(() => initialHours(settings), [settings])
  const doctorIds = useMemo(() => settings.doctors.map((doctor) => doctor.id), [settings])
  const [values, setValues] = useState<HoursValues>(initial)
  const [errors, setErrors] = useState<HoursErrors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const save = useSaveEfficiencySettings()
  const closeRef = useRef<(() => void) | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)
  const busy = save.isPending
  const dirty = values.minutes !== initial.minutes || doctorIds.some((id) => values.doctors[id] !== initial.doctors[id])

  const focusFirst = (found: HoursErrors) => {
    const first = ['minutes', ...doctorIds.map(doctorKey)].find((key) => found[key])
    if (first) globalThis.setTimeout(() => formRef.current?.querySelector<HTMLElement>(`[data-error-key="${first}"]`)?.focus(), 0)
  }

  const showServerError = (cause: unknown) => {
    if (!isApiError(cause)) return setGeneral(SERVER_TEXT)
    if (cause.kind === 'network') return setGeneral(NETWORK_TEXT)
    if (cause.kind !== 'validation') return setGeneral(SERVER_TEXT)
    const mapped: HoursErrors = {}
    for (const [field, code] of Object.entries(cause.fields)) {
      const found = serverError(field, code, doctorIds)
      if (found) mapped[found.key] = found.text
    }
    setErrors(mapped)
    focusFirst(mapped)
    if (Object.keys(mapped).length === 0) setGeneral('Проверьте значение')
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const result = checkHoursForm(values, doctorIds)
    setErrors(result.errors)
    if (!result.body) return focusFirst(result.errors)
    save.mutate(result.body, { onSuccess: onSaved, onError: showServerError })
  }

  return (
    <Dialog
      title={TITLE}
      subtitle={SUBTITLE}
      onClose={onClose}
      dirty={dirty}
      busy={busy}
      closeRef={closeRef}
      fallbackFocus={fallbackFocus}
      testId="efficiency-hours-dialog"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => closeRef.current?.()}>
            Отмена
          </button>
          <button type="submit" form="hours-form" className="btn btn--primary" disabled={busy} aria-busy={busy || undefined} data-testid="efficiency-hours-save">
            {busy ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </>
      }
    >
      <form id="hours-form" ref={formRef} noValidate onSubmit={submit}>
        <Field label="Средняя длительность приёма, минут" error={errors.minutes} errorTestId="efficiency-hours-field-minutes-error">
          {(control: FieldControlProps) => (
            <input
              {...control}
              className="input"
              inputMode="numeric"
              autoComplete="off"
              value={values.minutes}
              disabled={busy}
              data-error-key="minutes"
              data-testid="efficiency-hours-field-minutes"
              onChange={(event) => {
                setValues({ ...values, minutes: event.target.value })
                setErrors({ ...errors, minutes: '' })
              }}
            />
          )}
        </Field>
        <div className="hours__doctors">
          {settings.doctors.map((doctor) => {
            const key = doctorKey(doctor.id)
            return (
              <Field key={doctor.id} label={doctor.name} error={errors[key]} errorTestId={`efficiency-hours-field-${key}-error`}>
                {(control: FieldControlProps) => (
                  <div className="amount">
                    <input
                      {...control}
                      className="input"
                      inputMode="decimal"
                      autoComplete="off"
                      value={values.doctors[doctor.id] ?? ''}
                      disabled={busy}
                      data-error-key={key}
                      data-testid={`efficiency-hours-field-${key}`}
                      onChange={(event) => {
                        setValues({ ...values, doctors: { ...values.doctors, [doctor.id]: event.target.value } })
                        setErrors({ ...errors, [key]: '' })
                      }}
                    />
                    <span className="amount__unit" aria-hidden="true">
                      ч в неделю
                    </span>
                  </div>
                )}
              </Field>
            )
          })}
        </div>
        {general && <InlineAlert testId="efficiency-hours-error">{general}</InlineAlert>}
      </form>
    </Dialog>
  )
}
