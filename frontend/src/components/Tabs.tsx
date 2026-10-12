import { useRef, type KeyboardEvent, type ReactNode } from 'react'
import './Tabs.css'

export interface TabDef<Id extends string> {
  id: Id
  label: string
  /** Number of the list under the tab; null hides it, 'loading' shows a placeholder. */
  count?: number | null | 'loading'
}

export function tabElementId(prefix: string, id: string): string {
  return `${prefix}-tab-${id}`
}

export function panelElementId(prefix: string, id: string): string {
  return `${prefix}-panel-${id}`
}

interface TabsProps<Id extends string> {
  prefix: string
  label: string
  tabs: TabDef<Id>[]
  value: Id
  onChange: (id: Id) => void
}

/** Tabs with automatic activation: arrows move and select, Home and End jump (design/components.md, section 6). */
export function Tabs<Id extends string>({ prefix, label, tabs, value, onChange }: TabsProps<Id>) {
  const refs = useRef(new Map<string, HTMLButtonElement>())

  const move = (index: number) => {
    const target = tabs[(index + tabs.length) % tabs.length]
    if (!target) return
    onChange(target.id)
    refs.current.get(target.id)?.focus()
  }

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault()
        move(index + 1)
        break
      case 'ArrowLeft':
        event.preventDefault()
        move(index - 1)
        break
      case 'Home':
        event.preventDefault()
        move(0)
        break
      case 'End':
        event.preventDefault()
        move(tabs.length - 1)
        break
      default:
    }
  }

  return (
    <div className="seg" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => {
        const selected = tab.id === value
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={tabElementId(prefix, tab.id)}
            aria-selected={selected}
            aria-controls={panelElementId(prefix, tab.id)}
            tabIndex={selected ? 0 : -1}
            className={selected ? 'seg__btn seg__btn--on' : 'seg__btn'}
            ref={(node) => {
              if (node) refs.current.set(tab.id, node)
              else refs.current.delete(tab.id)
            }}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.label}
            {tab.count === 'loading' && <span className="seg__cnt seg__cnt--loading" aria-hidden="true" />}
            {typeof tab.count === 'number' && tab.count > 0 && <span className="seg__cnt">{tab.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

interface SegmentedOption<Id extends string> {
  id: Id
  label: string
}

interface SegmentedProps<Id extends string> {
  label: string
  options: SegmentedOption<Id>[]
  value: Id
  onChange: (id: Id) => void
  disabled?: boolean
}

/** Chooses a value of a form field (role radiogroup), same look as Tabs. */
export function Segmented<Id extends string>({ label, options, value, onChange, disabled = false }: SegmentedProps<Id>) {
  const refs = useRef(new Map<string, HTMLButtonElement>())

  const move = (index: number) => {
    const target = options[(index + options.length) % options.length]
    if (!target) return
    onChange(target.id)
    refs.current.get(target.id)?.focus()
  }

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault()
      move(index + 1)
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault()
      move(index - 1)
    }
  }

  return (
    <div className="seg seg--form" role="radiogroup" aria-label={label}>
      {options.map((option, index) => {
        const selected = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            className={selected ? 'seg__btn seg__btn--on' : 'seg__btn'}
            ref={(node) => {
              if (node) refs.current.set(option.id, node)
              else refs.current.delete(option.id)
            }}
            onClick={() => onChange(option.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function TabPanel({ prefix, id, children }: { prefix: string; id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={panelElementId(prefix, id)} aria-labelledby={tabElementId(prefix, id)} tabIndex={-1} className="tabpanel">
      {children}
    </div>
  )
}
