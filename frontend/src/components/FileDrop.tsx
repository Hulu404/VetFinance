import { useId, useRef, useState, type DragEvent } from 'react'
import { formatFileSize } from '../lib/dates'
import './FileDrop.css'

interface FileDropProps {
  file: File | null
  onFile: (file: File | null) => void
  error?: string | null
  disabled?: boolean
  /** Short format hint under the buttons: "Формат 1С, файл .txt, до 10 МБ". */
  formatHint: string
  accept: string
  inputTestId?: string
}

/** File picker with drag and drop as an addition: the button works from the keyboard (design/components.md, section 10). */
export function FileDrop({ file, onFile, error, disabled = false, formatHint, accept, inputTestId }: FileDropProps) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const errorId = useId()
  const [dragging, setDragging] = useState(false)

  const pick = (list: FileList | null) => {
    const first = list?.item(0) ?? null
    if (first) onFile(first)
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (!disabled) pick(event.dataTransfer.files)
  }

  const classes = ['drop']
  if (dragging) classes.push('drop--over')
  if (file) classes.push('drop--picked')
  if (error) classes.push('drop--error')
  if (disabled) classes.push('drop--disabled')

  return (
    <div>
      <div
        className={classes.join(' ')}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          className="drop__input"
          accept={accept}
          tabIndex={-1}
          disabled={disabled}
          data-testid={inputTestId}
          aria-label="Файл выписки"
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => {
            pick(event.target.files)
            event.target.value = ''
          }}
        />
        {file ? (
          <div className="drop__picked">
            <span className="drop__name" title={file.name}>
              {file.name}
            </span>
            <span className="drop__size">{formatFileSize(file.size)}</span>
            {!disabled && (
              <button type="button" className="btn btn--text" onClick={() => onFile(null)}>
                Убрать
              </button>
            )}
            <span className="sr-only" role="status">
              Выбран файл {file.name}, {formatFileSize(file.size)}
            </span>
          </div>
        ) : (
          <>
            <p className="drop__title">{dragging ? 'Отпустите файл' : 'Перетащите выписку сюда'}</p>
            <button type="button" className="btn" disabled={disabled} onClick={() => inputRef.current?.click()}>
              Выбрать файл
            </button>
            <p className="drop__hint">{formatHint}</p>
          </>
        )}
      </div>
      {error && (
        <p id={errorId} className="fld__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
