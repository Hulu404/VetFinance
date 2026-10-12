import { useId, type ReactNode } from 'react'
import './Field.css'

export interface FieldControlProps {
  id: string
  'aria-invalid': boolean | undefined
  'aria-describedby': string | undefined
}

interface FieldProps {
  label: string
  /** Appends "(необязательно)" to the label. */
  optional?: boolean
  hint?: ReactNode
  error?: string | null
  children: (control: FieldControlProps) => ReactNode
}

/** Label, control, hint and error message, wired through id and aria-describedby (design/components.md, section 5). */
export function Field({ label, optional = false, hint, error, children }: FieldProps) {
  const id = useId()
  const messageId = `${id}-msg`
  const hasMessage = Boolean(error) || Boolean(hint)
  return (
    <div className="fld">
      <label className="fld__label" htmlFor={id}>
        {label}
        {optional && <span className="fld__optional"> (необязательно)</span>}
      </label>
      {children({
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': hasMessage ? messageId : undefined,
      })}
      {error ? (
        <p id={messageId} className="fld__error">
          {error}
        </p>
      ) : hint ? (
        <p id={messageId} className="fld__hint">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function CheckField({
  label,
  checked,
  onChange,
  disabled = false,
  testId,
  describedBy,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  testId?: string
  describedBy?: string
}) {
  const id = useId()
  return (
    <label className={disabled ? 'chk chk--disabled' : 'chk'} htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        className="chk__box"
        checked={checked}
        disabled={disabled}
        data-testid={testId}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
    </label>
  )
}
