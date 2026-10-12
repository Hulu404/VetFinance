import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import './Dialog.css'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => !element.closest('[hidden]') && element.getAttribute('aria-hidden') !== 'true',
  )
}

let scrollLocks = 0

function lockScroll(): () => void {
  scrollLocks += 1
  if (scrollLocks === 1) document.body.style.overflow = 'hidden'
  return () => {
    scrollLocks = Math.max(0, scrollLocks - 1)
    if (scrollLocks === 0) document.body.style.overflow = ''
  }
}

export interface DialogProps {
  title: string
  subtitle?: string
  /** 540px instead of 480px (statement upload). */
  wide?: boolean
  /** Called when the person leaves the dialog (after the discard question, if any). */
  onClose: () => void
  /** The form was changed: Esc, the cross and "Отмена" first ask "Закрыть без сохранения?". */
  dirty?: boolean
  /** A request is going: the dialog cannot be closed. */
  busy?: boolean
  /** Hide the cross (the dialog has its own close control, e.g. "Прервать"). */
  hideClose?: boolean
  /** Where focus goes on close when the opener no longer exists (e.g. the row left the list). */
  fallbackFocus?: () => void
  testId?: string
  /** Role "alertdialog" for confirmations. */
  alert?: boolean
  children: ReactNode
  footer?: ReactNode
  /** Reports the function that asks to close (Esc / cross semantics) so the footer "Отмена" can use it. */
  closeRef?: { current: (() => void) | null }
}

/** Native modal <dialog>: focus is trapped, Esc closes, a click on the backdrop does not (design/components.md, section 9). */
export function Dialog({
  title,
  subtitle,
  wide = false,
  onClose,
  dirty = false,
  busy = false,
  hideClose = false,
  fallbackFocus,
  testId,
  alert = false,
  children,
  footer,
  closeRef,
}: DialogProps) {
  const titleId = useId()
  const subtitleId = useId()
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const closedRef = useRef(false)
  const [confirming, setConfirming] = useState(false)
  const onCloseRef = useRef(onClose)
  const fallbackRef = useRef(fallbackFocus)

  useEffect(() => {
    onCloseRef.current = onClose
    fallbackRef.current = fallbackFocus
  })

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal()
    else dialog.setAttribute('open', '')
    const unlock = lockScroll()

    const body = bodyRef.current
    const target =
      body?.querySelector<HTMLElement>('[data-autofocus]') ?? (body ? focusableIn(body)[0] : undefined) ?? dialog
    target.focus()

    return () => {
      unlock()
      if (dialog.open && typeof dialog.close === 'function') dialog.close()
      const opener = openerRef.current
      if (opener && opener.isConnected) opener.focus()
      else fallbackRef.current?.()
    }
  }, [])

  const requestClose = useCallback(() => {
    if (busy || closedRef.current) return
    if (dirty) {
      setConfirming(true)
      return
    }
    closedRef.current = true
    onCloseRef.current()
  }, [busy, dirty])

  useEffect(() => {
    if (!closeRef) return
    closeRef.current = requestClose
    return () => {
      closeRef.current = null
    }
  }, [closeRef, requestClose])

  const discard = () => {
    if (closedRef.current) return
    closedRef.current = true
    onCloseRef.current()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key === 'Escape') {
      // An open figure tip closes first (it listens to Esc itself); the dialog stays.
      if (document.querySelector('[role="tooltip"]')) return
      event.preventDefault()
      event.stopPropagation()
      if (confirming) setConfirming(false)
      else requestClose()
      return
    }
    if (event.key !== 'Tab') return
    const dialog = dialogRef.current
    if (!dialog) return
    const items = focusableIn(dialog)
    if (items.length === 0) {
      event.preventDefault()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement
    if (event.shiftKey && (active === first || active === dialog)) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className={wide ? 'dlg dlg--wide' : 'dlg'}
      aria-labelledby={titleId}
      aria-describedby={subtitle ? subtitleId : undefined}
      aria-modal="true"
      role={alert ? 'alertdialog' : undefined}
      data-testid={testId}
      onKeyDown={onKeyDown}
      onCancel={(event) => {
        // Esc is handled in onKeyDown; this keeps the browser from closing the dialog behind our back.
        event.preventDefault()
      }}
    >
      <div className="dlg__panel">
        <div hidden={confirming} className="dlg__main">
          <header className="dlg__head">
            <div className="dlg__titles">
              <h2 id={titleId} className="dlg__title">
                {title}
              </h2>
              {subtitle && (
                <p id={subtitleId} className="dlg__subtitle">
                  {subtitle}
                </p>
              )}
            </div>
            {!hideClose && (
              <button type="button" className="dlg__close" aria-label="Закрыть" onClick={requestClose} disabled={busy}>
                <span aria-hidden="true">✕</span>
              </button>
            )}
          </header>
          <div ref={bodyRef} className="dlg__body">
            {children}
          </div>
          {footer && <footer className="dlg__foot">{footer}</footer>}
        </div>
        {confirming && (
          <div className="dlg__confirm" role="alertdialog" aria-labelledby={`${titleId}-c`}>
            <h2 id={`${titleId}-c`} className="dlg__title">
              Закрыть без сохранения?
            </h2>
            <p className="dlg__subtitle">Введённые данные пропадут.</p>
            <div className="dlg__foot">
              <button type="button" className="btn btn--primary" data-autofocus ref={(node) => node?.focus()} onClick={() => setConfirming(false)}>
                Остаться
              </button>
              <button type="button" className="btn btn--danger" onClick={discard}>
                Закрыть
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  )
}
