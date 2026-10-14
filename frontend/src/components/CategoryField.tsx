import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { Category, CategoryType } from '../api/types'
import { pluralRu } from '../lib/format'
import './CategoryField.css'

const GROUPS: { type: CategoryType; label: string }[] = [
  { type: 'income', label: 'Доходы' },
  { type: 'variable', label: 'Переменные расходы' },
  { type: 'fixed', label: 'Постоянные расходы' },
]

function normalize(text: string): string {
  return text.toLowerCase().replaceAll('ё', 'е')
}

/** Income operations choose among income categories, outgoing ones among expenses. */
function categoriesFor(items: Category[], kind: 'in' | 'out'): Category[] {
  return items.filter((item) => (kind === 'in' ? item.type === 'income' : item.type !== 'income'))
}

interface CategoryFieldProps {
  label: string
  optional?: boolean
  categories: Category[] | undefined
  loading: boolean
  loadError: boolean
  onRetry: () => void
  kind: 'in' | 'out'
  value: string | null
  onChange: (id: string) => void
  error?: string | null
  disabled?: boolean
  /** Open the list at once (the category dialog exists to choose one). */
  defaultOpen?: boolean
  testId?: string
}

/** Combobox with a filtered, grouped list (design/components.md, section 7). The list is drawn in the page flow. */
export function CategoryField({
  label,
  optional = false,
  categories,
  loading,
  loadError,
  onRetry,
  kind,
  value,
  onChange,
  error,
  disabled = false,
  defaultOpen = false,
  testId,
}: CategoryFieldProps) {
  const id = useId()
  const listId = `${id}-list`
  const errorId = `${id}-err`
  const [open, setOpen] = useState(defaultOpen)
  const [query, setQuery] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const available = useMemo(() => categoriesFor(categories ?? [], kind), [categories, kind])
  const selected = available.find((item) => item.id === value) ?? null

  const visible = useMemo(() => {
    const needle = query ? normalize(query.trim()) : ''
    return needle ? available.filter((item) => normalize(item.name).includes(needle)) : available
  }, [available, query])

  const groups = GROUPS.map((group) => ({
    ...group,
    items: visible.filter((item) => item.type === group.type),
  })).filter((group) => group.items.length > 0)

  // Close the list when focus leaves the whole field, not when it moves between input and options.
  useEffect(() => {
    if (!open) return
    const onFocusIn = (event: FocusEvent) => {
      if (wrapperRef.current && event.target instanceof Node && !wrapperRef.current.contains(event.target)) {
        setOpen(false)
        setQuery(null)
      }
    }
    document.addEventListener('focusin', onFocusIn)
    return () => document.removeEventListener('focusin', onFocusIn)
  }, [open])

  const choose = (categoryId: string) => {
    onChange(categoryId)
    setQuery(null)
    setOpen(false)
    setActiveId(null)
    inputRef.current?.focus()
  }

  const moveActive = (delta: number) => {
    if (visible.length === 0) return
    const index = visible.findIndex((item) => item.id === activeId)
    const next = index === -1 ? (delta > 0 ? 0 : visible.length - 1) : (index + delta + visible.length) % visible.length
    setActiveId(visible[next]?.id ?? null)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        if (!open) setOpen(true)
        else moveActive(1)
        break
      case 'ArrowUp':
        event.preventDefault()
        if (!open) setOpen(true)
        else moveActive(-1)
        break
      case 'Enter':
        if (open && activeId) {
          event.preventDefault()
          choose(activeId)
        }
        break
      case 'Escape':
        // The first Esc closes the list, the second one closes the dialog.
        if (open) {
          event.preventDefault()
          event.stopPropagation()
          setOpen(false)
          setQuery(null)
        }
        break
      default:
    }
  }

  const placeholder = loading ? 'Загружаем статьи…' : 'Выберите статью'
  const displayValue = query ?? selected?.name ?? ''
  const showList = open && !loading && !loadError
  const foundText = `Найдено ${visible.length} ${pluralRu(visible.length, 'статья', 'статьи', 'статей')}`

  return (
    <div className="fld catf" ref={wrapperRef}>
      <label className="fld__label" htmlFor={id}>
        {label}
        {optional && <span className="fld__optional"> (необязательно)</span>}
      </label>
      <div className="catf__box">
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          className="input catf__input"
          autoComplete="off"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && activeId ? `${id}-opt-${activeId}` : undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          placeholder={placeholder}
          disabled={disabled || loading || loadError}
          value={displayValue}
          data-autofocus={defaultOpen ? '' : undefined}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
            setActiveId(null)
          }}
          onClick={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        <span className="catf__arrow" aria-hidden="true">
          ▾
        </span>
      </div>
      {showList && (
        <div className="catf__list" role="listbox" id={listId} aria-label={label} data-testid={testId}>
          {groups.map((group) => (
            <div key={group.type} role="group" aria-label={group.label}>
              <p className="catf__group" aria-hidden="true">
                {group.label}
              </p>
              {group.items.map((item) => {
                const isSelected = item.id === value
                return (
                  <div
                    key={item.id}
                    id={`${id}-opt-${item.id}`}
                    role="option"
                    aria-selected={isSelected}
                    tabIndex={-1}
                    className={item.id === activeId ? 'catf__opt catf__opt--active' : 'catf__opt'}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => choose(item.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        choose(item.id)
                      }
                    }}
                  >
                    {item.name}
                    {isSelected && (
                      <span className="catf__check" aria-hidden="true">
                        ✓
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
          {available.length === 0 && <p className="catf__empty">Статей пока нет.</p>}
          {available.length > 0 && visible.length === 0 && (
            <p className="catf__empty">Такой статьи нет. Список статей настраивается в разделе Настройки → Категории.</p>
          )}
        </div>
      )}
      <p className="sr-only" aria-live="polite">
        {showList && query ? foundText : ''}
      </p>
      {loadError && (
        <p className="fld__error">
          Не получилось загрузить статьи.{' '}
          <button type="button" className="btn btn--text" onClick={onRetry}>
            Повторить
          </button>
        </p>
      )}
      {error && (
        <p id={errorId} className="fld__error">
          {error}
        </p>
      )}
    </div>
  )
}
