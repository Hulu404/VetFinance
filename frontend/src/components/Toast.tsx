import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import './Toast.css'

const SUCCESS_MS = 8000
const MAX_TOASTS = 3

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastOptions {
  message: string
  action?: ToastAction
  /** Error toasts stay until closed and are announced as alerts. */
  kind?: 'success' | 'error'
}

interface ToastItem extends ToastOptions {
  id: number
}

interface ToastApi {
  show: (options: ToastOptions) => void
}

const ToastContext = createContext<ToastApi>({ show: () => undefined })

export function useToast(): ToastApi {
  return useContext(ToastContext)
}

function ToastView({ item, onClose }: { item: ToastItem; onClose: (id: number) => void }) {
  const timer = useRef<number | undefined>(undefined)
  const isError = item.kind === 'error'

  const start = useCallback(() => {
    if (isError) return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => onClose(item.id), SUCCESS_MS)
  }, [isError, item.id, onClose])
  const pause = () => window.clearTimeout(timer.current)

  useEffect(() => {
    start()
    return () => window.clearTimeout(timer.current)
  }, [start])

  return (
    // The handlers only pause the timer while the pointer or focus is inside; the controls inside are native buttons.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div
      className="toast"
      onMouseEnter={pause}
      onMouseLeave={start}
      onFocus={pause}
      onBlur={start}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose(item.id)
      }}
    >
      <div className="toast__text">
        {isError && <span className="sr-only">Ошибка: </span>}
        <p>{item.message}</p>
        {item.action && (
          <button
            type="button"
            className="toast__action"
            onClick={() => {
              item.action?.onClick()
              onClose(item.id)
            }}
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button type="button" className="toast__close" aria-label="Закрыть уведомление" onClick={() => onClose(item.id)}>
        <span aria-hidden="true">✕</span>
      </button>
    </div>
  )
}

/** Toast zone is mounted once with the app, so screen readers get a live region that already exists. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const close = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id))
  }, [])

  const show = useCallback((options: ToastOptions) => {
    const id = nextId.current++
    setItems((current) => [...current, { ...options, id }].slice(-MAX_TOASTS))
  }, [])

  const api = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-zone">
        <div role="status" className="toast-zone__list">
          {items
            .filter((item) => item.kind !== 'error')
            .map((item) => (
              <ToastView key={item.id} item={item} onClose={close} />
            ))}
        </div>
        <div role="alert" className="toast-zone__list">
          {items
            .filter((item) => item.kind === 'error')
            .map((item) => (
              <ToastView key={item.id} item={item} onClose={close} />
            ))}
        </div>
      </div>
    </ToastContext.Provider>
  )
}
