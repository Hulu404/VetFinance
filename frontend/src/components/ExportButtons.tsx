import { useEffect, useRef, useState } from 'react'
import { apiDownload } from '../api/client'
import { isApiError } from '../api/errors'
import type { ExportFormat, ReportName } from '../api/types'
import { saveBlob } from '../lib/saveBlob'
import { useToast } from './Toast'
import './ExportButtons.css'

const SLOW_EXPORT_MS = 10_000
export const EXPORT_ERROR_TEXT = 'Не получилось подготовить файл. Попробуйте ещё раз.'
export const EXPORT_RATE_LIMIT_TEXT = 'Слишком много запросов. Подождите минуту.'

interface ExportButtonsProps {
  report: ReportName
  /** Month on the screen; the stock report has none and asks for its default. */
  month?: string | null
  asOf?: string | null
  /** The report is loading or empty: the buttons stay but do nothing (`aria-disabled`). */
  disabled: boolean
}

function exportPath(report: ReportName, format: ExportFormat, month: string | null | undefined, asOf: string | null | undefined) {
  const params = new URLSearchParams({ format })
  if (month) params.set('month', month)
  if (asOf) params.set('as_of', asOf)
  return `/v1/reports/${report}/export?${params.toString()}`
}

/** "Скачать Excel" and "Скачать PDF" (design/components.md, section 22). The file is fetched with the token and saved as a Blob. */
export function ExportButtons({ report, month, asOf, disabled }: ExportButtonsProps) {
  const toast = useToast()
  const [busy, setBusy] = useState<ExportFormat | null>(null)
  const [slow, setSlow] = useState(false)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    if (!busy) {
      setSlow(false)
      return
    }
    const timer = window.setTimeout(() => setSlow(true), SLOW_EXPORT_MS)
    return () => window.clearTimeout(timer)
  }, [busy])

  const inactive = disabled || busy !== null

  const run = async (format: ExportFormat) => {
    if (inactive) return
    setBusy(format)
    try {
      const file = await apiDownload(exportPath(report, format, month, asOf))
      const name = file.filename ?? `vetfinance-${report}-${month ?? 'current'}.${format}`
      saveBlob(file.blob, name)
      toast.show({ message: `Файл готов: ${name}`, kind: 'success' })
    } catch (error) {
      const limited = isApiError(error) && error.kind === 'rate_limited'
      toast.show({ message: limited ? EXPORT_RATE_LIMIT_TEXT : EXPORT_ERROR_TEXT, kind: 'error' })
    } finally {
      if (alive.current) setBusy(null)
    }
  }

  const button = (format: ExportFormat, label: string) => (
    <button
      type="button"
      className="btn export-btn"
      aria-disabled={inactive}
      aria-busy={busy === format}
      data-testid={`${report}-export-${format}`}
      onClick={() => void run(format)}
    >
      {busy === format ? 'Готовим файл…' : label}
    </button>
  )

  return (
    <div className="export-buttons">
      <div className="export-buttons__row">
        {button('xlsx', 'Скачать Excel')}
        {button('pdf', 'Скачать PDF')}
      </div>
      {slow && <p className="export-buttons__slow">Готовим дольше обычного. Подождите ещё немного.</p>}
    </div>
  )
}
