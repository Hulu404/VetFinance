import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { StockItem } from '../../api/types'
import { formatMoney, pluralRu } from '../../lib/format'
import '../../components/CategoryField.css'

function normalize(text: string): string {
  return text.toLowerCase().replaceAll('ё', 'е')
}

/** "по 140 ₽ за фл." or the words that the item will not be counted. The price is the one of the warehouse, not computed. */
export function unitCostText(item: Pick<StockItem, 'unit' | 'unit_cost'>): string {
  return item.unit_cost ? `по ${formatMoney(item.unit_cost.value)} за ${item.unit}` : 'нет цены закупки, позиция не будет учтена'
}

interface StockItemFieldProps {
  label: string
  items: StockItem[] | undefined
  loading: boolean
  loadError: boolean
  onRetry: () => void
  value: string | null
  /** The chosen item may be missing from the loaded page; its name is then shown from here. */
  valueName?: string
  onChange: (id: string) => void
  error?: string | null
  disabled?: boolean
  testId?: string
  errorTestId?: string
}

/** Combobox with a filtered list of warehouse items (design/screens/price.md, "Техкарта и параметры"). */
export function StockItemField({ label, items, loading, loadError, onRetry, value, valueName, onChange, error, disabled = false, testId, errorTestId }: StockItemFieldProps) {
  const id = useId()
  const listId = `${id}-list`
  const errorId = `${id}-err`
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const all = useMemo(() => items ?? [], [items])
  const selected = all.find((item) => item.id === value) ?? null
  const visible = useMemo(() => {
    const needle = query ? normalize(query.trim()) : ''
    return needle ? all.filter((item) => normalize(item.name).includes(needle)) : all
  }, [all, query])

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

  const choose = (itemId: string) => {
    onChange(itemId)
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
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) setOpen(true)
      else moveActive(event.key === 'ArrowDown' ? 1 : -1)
    } else if (event.key === 'Enter' && open && activeId) {
      event.preventDefault()
      choose(activeId)
    } else if (event.key === 'Escape' && open) {
      event.preventDefault()
      event.stopPropagation()
      setOpen(false)
      setQuery(null)
    }
  }

  const showList = open && !loading && !loadError
  const displayValue = query ?? selected?.name ?? valueName ?? ''
  return (
    <div className="fld catf" ref={wrapperRef}>
      <label className="fld__label" htmlFor={id}>
        {label}
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
          placeholder={loading ? 'Загружаем склад…' : 'Выберите позицию'}
          disabled={disabled || loading || loadError}
          value={displayValue}
          data-testid={testId}
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
        <div className="catf__list" role="listbox" id={listId} aria-label={label}>
          {visible.map((item) => (
            <div
              key={item.id}
              id={`${id}-opt-${item.id}`}
              role="option"
              aria-selected={item.id === value}
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
              <span className="fld__hint">{item.unit}</span>
            </div>
          ))}
          {visible.length === 0 && <p className="catf__empty">{all.length === 0 ? 'На складе пока ничего нет.' : 'Такой позиции на складе нет.'}</p>}
        </div>
      )}
      <p className="sr-only" aria-live="polite">
        {showList && query ? `Найдено ${visible.length} ${pluralRu(visible.length, 'позиция', 'позиции', 'позиций')}` : ''}
      </p>
      {selected && !error && <p className="fld__hint">{unitCostText(selected)}</p>}
      {loadError && (
        <p className="fld__error">
          Не получилось загрузить склад.{' '}
          <button type="button" className="btn btn--text" onClick={onRetry}>
            Повторить
          </button>
        </p>
      )}
      {error && (
        <p id={errorId} className="fld__error" data-testid={errorTestId}>
          {error}
        </p>
      )}
    </div>
  )
}
