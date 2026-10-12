import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type FocusEvent,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type Ref,
} from 'react'
import { createPortal } from 'react-dom'
import type { Figure } from '../api/types'
import { formatByUnit, formatFigure, sourceLabel } from '../lib/format'
import './FigureTip.css'

const HOVER_OPEN_DELAY_MS = 80
const HOVER_CLOSE_DELAY_MS = 120
const TIP_GAP_PX = 8
const VIEWPORT_MARGIN_PX = 12
const SWALLOW_CLICK_MS = 400

export interface FigureTipTriggerProps {
  ref: Ref<HTMLButtonElement>
  onPointerEnter: (event: PointerEvent) => void
  onPointerLeave: (event: PointerEvent) => void
  onPointerDown: (event: PointerEvent) => void
  onFocus: (event: FocusEvent) => void
  onBlur: (event: FocusEvent) => void
  onClick: (event: { detail: number }) => void
  onKeyDown: (event: KeyboardEvent) => void
  'aria-describedby': string | undefined
  'aria-expanded': boolean
  'data-testid': string
}

interface FigureTipProps {
  figure: Figure
  /** Name of the metric, shown as the label in the tip (the Figure has no title of its own). */
  title: string
  emoji?: string
  /** Renders the element that opens the tip. Spread the given props on one focusable element. */
  children: (triggerProps: FigureTipTriggerProps) => ReactNode
}

type PointerKind = 'mouse' | 'touch' | 'pen' | null

// Only one tip is open at a time.
let closeActiveTip: (() => void) | null = null

interface Position {
  top: number
  left: number
}

function computePosition(anchor: DOMRect, tip: DOMRect): Position {
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const fitsBelow = anchor.bottom + TIP_GAP_PX + tip.height <= viewportHeight - VIEWPORT_MARGIN_PX
  const fitsAbove = anchor.top - TIP_GAP_PX - tip.height >= VIEWPORT_MARGIN_PX
  const top = fitsBelow || !fitsAbove ? anchor.bottom + TIP_GAP_PX : anchor.top - TIP_GAP_PX - tip.height
  const centered = anchor.left + anchor.width / 2 - tip.width / 2
  const maxLeft = Math.max(VIEWPORT_MARGIN_PX, viewportWidth - tip.width - VIEWPORT_MARGIN_PX)
  const left = Math.min(Math.max(centered, VIEWPORT_MARGIN_PX), maxLeft)
  return { top, left }
}

export function FigureTip({ figure, title, emoji, children }: FigureTipProps) {
  const tipId = useId()
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const tipRef = useRef<HTMLDivElement | null>(null)
  const openTimer = useRef<number | undefined>(undefined)
  const closeTimer = useRef<number | undefined>(undefined)
  const lastPointer = useRef<PointerKind>(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<Position | null>(null)

  const clearTimers = useCallback(() => {
    window.clearTimeout(openTimer.current)
    window.clearTimeout(closeTimer.current)
  }, [])

  const close = useCallback(() => {
    clearTimers()
    setOpen(false)
    setPosition(null)
    if (closeActiveTip === close) closeActiveTip = null
  }, [clearTimers])

  const show = useCallback(() => {
    clearTimers()
    if (closeActiveTip && closeActiveTip !== close) closeActiveTip()
    closeActiveTip = close
    setOpen(true)
  }, [clearTimers, close])

  useEffect(() => () => {
    clearTimers()
    if (closeActiveTip === close) closeActiveTip = null
  }, [clearTimers, close])

  // Place the tip next to the trigger once its size is known; keep it attached on scroll and resize.
  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const anchor = triggerRef.current
      const tip = tipRef.current
      if (!anchor || !tip) return
      setPosition(computePosition(anchor.getBoundingClientRect(), tip.getBoundingClientRect()))
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open])

  // Esc closes (focus stays on the trigger); a tap outside closes and is not passed to what lies under it.
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    const onPointerDown = (event: globalThis.PointerEvent) => {
      const target = event.target as Node | null
      if (target && (triggerRef.current?.contains(target) || tipRef.current?.contains(target))) return
      close()
      if (event.pointerType === 'touch') {
        const swallow = (clickEvent: Event) => {
          clickEvent.stopPropagation()
          clickEvent.preventDefault()
        }
        document.addEventListener('click', swallow, { capture: true, once: true })
        window.setTimeout(() => document.removeEventListener('click', swallow, true), SWALLOW_CLICK_MS)
      }
    }
    const onScroll = () => {
      if (lastPointer.current === 'touch') close()
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown, true)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown, true)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [open, close])

  const scheduleClose = () => {
    window.clearTimeout(openTimer.current)
    window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(close, HOVER_CLOSE_DELAY_MS)
  }

  const triggerProps: FigureTipTriggerProps = {
    ref: triggerRef,
    onPointerEnter: (event) => {
      if (event.pointerType === 'touch') return
      window.clearTimeout(closeTimer.current)
      window.clearTimeout(openTimer.current)
      openTimer.current = window.setTimeout(show, HOVER_OPEN_DELAY_MS)
    },
    onPointerLeave: (event) => {
      if (event.pointerType === 'touch') return
      scheduleClose()
    },
    onPointerDown: (event) => {
      lastPointer.current = event.pointerType as PointerKind
    },
    onFocus: () => {
      // Keyboard focus opens at once; focus that comes from a pointer is handled by hover and click.
      if (lastPointer.current === null) show()
    },
    onBlur: () => {
      lastPointer.current = null
      close()
    },
    onClick: (event) => {
      const fromMouse = lastPointer.current === 'mouse' && event.detail > 0
      if (fromMouse) {
        // Mouse: hover already opens the tip, a click must not close it.
        show()
        return
      }
      if (open) close()
      else show()
    },
    onKeyDown: (event) => {
      if (event.key === 'Escape' && open) {
        event.preventDefault()
        close()
      }
    },
    'aria-describedby': open ? tipId : undefined,
    'aria-expanded': open,
    'data-testid': 'figure-tip-trigger',
  }

  const style: CSSProperties = position
    ? { top: position.top, left: position.left }
    : { top: 0, left: 0, visibility: 'hidden' }

  return (
    <>
      {children(triggerProps)}
      {open &&
        createPortal(
          <div
            ref={tipRef}
            id={tipId}
            role="tooltip"
            data-testid="figure-tip"
            className="figure-tip"
            style={style}
            onPointerEnter={() => window.clearTimeout(closeTimer.current)}
            onPointerLeave={(event) => event.pointerType !== 'touch' && scheduleClose()}
          >
            <TipBody figure={figure} title={title} emoji={emoji} />
          </div>,
          // A modal dialog sits in the top layer, above any z-index: inside a dialog the tip is drawn in it.
          triggerRef.current?.closest('dialog') ?? document.body,
        )}
    </>
  )
}

function TipBody({ figure, title, emoji }: { figure: Figure; title: string; emoji?: string }) {
  const breakdown = figure.breakdown ?? []
  const sources = figure.source ?? []
  const hasFooter = Boolean(figure.note) || sources.length > 0
  return (
    <>
      <span className="figure-tip__tag">{title}</span>
      <p className="figure-tip__value">
        {emoji ? <span aria-hidden="true">{emoji} </span> : null}
        {formatFigure(figure)}
      </p>
      {breakdown.length > 0 && (
        <ul className="figure-tip__rows">
          {breakdown.map((row, index) => (
            <li key={`${row.label}-${index}`} className="figure-tip__row">
              <span className="figure-tip__label">{row.label}</span>
              <span className={row.value < 0 ? 'figure-tip__amount figure-tip__amount--neg' : 'figure-tip__amount'}>
                {formatByUnit(row.value, row.unit)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {hasFooter && (
        <div className="figure-tip__footer">
          {figure.note ? <p className="figure-tip__note">{figure.note}</p> : null}
          {sources.length > 0 && (
            <p className="figure-tip__sources">
              <span>Источник:</span>
              {sources.map((source) => (
                <span key={source} className="figure-tip__chip">
                  {sourceLabel(source)}
                </span>
              ))}
            </p>
          )}
        </div>
      )}
    </>
  )
}
