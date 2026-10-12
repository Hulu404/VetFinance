import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiUpload, type UploadHandle } from '../../api/client'
import { useAccounts, invalidateAfterOperationChange } from '../../api/queries'
import type { ImportResult } from '../../api/types'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { FileDrop } from '../../components/FileDrop'
import { ProgressBar } from '../../components/ProgressBar'
import { InlineAlert } from '../../components/StateBlocks'
import { formatDateLong, formatDayMonth } from '../../lib/dates'
import { formatCount, pluralRu } from '../../lib/format'
import { checkStatementFile, importFailure } from './importErrors'

const SLOW_UPLOAD_MS = 30_000
const FROM_FILE = ''

interface ImportDialogProps {
  /** Account chosen in advance (the bank settings open the dialog from a row). */
  accountId?: string
  onClose: () => void
  onOpenTab: (tab: 'check' | 'duplicates') => void
}

type Phase = { name: 'select' } | { name: 'uploading'; percent: number | null } | { name: 'done'; result: ImportResult }

function Counter({ label, value, testId }: { label: string; value: number; testId: string }) {
  return (
    <div className="imp-counter">
      <dt>{label}</dt>
      <dd data-testid={testId}>{formatCount(value)}</dd>
    </div>
  )
}

function periodText(result: ImportResult): string {
  return `${result.account.name} · операции с ${formatDayMonth(result.period.from)} по ${formatDateLong(result.period.to)}`
}

function ResultView({ result }: { result: ImportResult }) {
  const nothingNew = result.loaded === 0
  return (
    <div data-testid="import-result" role="status">
      <p className="imp-period">{periodText(result)}</p>
      <p className="sr-only">
        Загружено {result.loaded}, дублей {result.duplicates}, на проверку {result.to_check}
      </p>
      {nothingNew && (
        <p className="imp-nothing">Эти операции уже были загружены, новых нет. Ничего не добавлено и не задвоено.</p>
      )}
      <dl className="imp-counters" aria-hidden="true">
        <Counter label="Загружено" value={result.loaded} testId="import-loaded" />
        {!nothingNew && <Counter label="Дублей" value={result.duplicates} testId="import-duplicates" />}
        {!nothingNew && <Counter label="На проверку" value={result.to_check} testId="import-to-check" />}
        {result.already_loaded > 0 && <Counter label="Уже были в учёте" value={result.already_loaded} testId="import-already-loaded" />}
      </dl>
      {!nothingNew && <p className="imp-hint">Дубли и операции без статьи вы разберёте в соответствующих вкладках.</p>}
      {result.skipped > 0 && (
        <p className="imp-skipped">
          Не удалось прочитать {result.skipped} {pluralRu(result.skipped, 'строку', 'строки', 'строк')} файла, они пропущены.
        </p>
      )}
    </div>
  )
}

export function ImportDialog({ accountId: presetAccountId, onClose, onOpenTab }: ImportDialogProps) {
  const queryClient = useQueryClient()
  const accounts = useAccounts()
  const bankAccounts = (accounts.data?.items ?? []).filter((item) => item.kind === 'bank')
  const only = bankAccounts.length === 1 ? bankAccounts[0] : undefined

  const [phase, setPhase] = useState<Phase>({ name: 'select' })
  const [file, setFile] = useState<File | null>(null)
  const [pickedAccount, setPickedAccount] = useState<string | null>(presetAccountId ?? null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [blockError, setBlockError] = useState<string | null>(null)
  const [slow, setSlow] = useState(false)
  const handle = useRef<UploadHandle<ImportResult> | null>(null)
  const closeRef = useRef<(() => void) | null>(null)

  const accountId = pickedAccount ?? only?.id ?? FROM_FILE
  const uploading = phase.name === 'uploading'

  useEffect(() => {
    if (!uploading) {
      setSlow(false)
      return
    }
    const timer = window.setTimeout(() => setSlow(true), SLOW_UPLOAD_MS)
    return () => window.clearTimeout(timer)
  }, [uploading])

  useEffect(() => () => handle.current?.abort(), [])

  const chooseFile = (next: File | null) => {
    setBlockError(null)
    setFile(next)
    setFileError(next ? checkStatementFile(next) : null)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!file) {
      setFileError('Выберите файл выписки')
      return
    }
    const localError = checkStatementFile(file)
    if (localError) {
      setFileError(localError)
      return
    }
    setFileError(null)
    setBlockError(null)
    const form = new FormData()
    form.append('file', file)
    if (accountId) form.append('account_id', accountId)
    setPhase({ name: 'uploading', percent: 0 })
    const upload = apiUpload<ImportResult>('/v1/imports/bank-statement', form, {
      onProgress: (percent) => setPhase({ name: 'uploading', percent }),
      onSent: () => setPhase({ name: 'uploading', percent: null }),
    })
    handle.current = upload
    upload.promise.then(
      (result) => {
        handle.current = null
        setPhase({ name: 'done', result })
        void invalidateAfterOperationChange(queryClient)
      },
      (error: unknown) => {
        handle.current = null
        if (error instanceof DOMException && error.name === 'AbortError') {
          setPhase({ name: 'select' })
          return
        }
        const failure = importFailure(error)
        setFileError(failure.fileError ?? null)
        setBlockError(failure.blockError ?? null)
        setPhase({ name: 'select' })
      },
    )
  }

  if (phase.name === 'done') {
    const { result } = phase
    return (
      <Dialog title="Выписка загружена" wide onClose={onClose} testId="import-dialog" closeRef={closeRef}
        footer={
          <>
            {result.to_check > 0 && (
              <button type="button" className="btn" onClick={() => { onClose(); onOpenTab('check') }}>
                Показать на проверку
              </button>
            )}
            {result.duplicates > 0 && (
              <button type="button" className="btn" onClick={() => { onClose(); onOpenTab('duplicates') }}>
                Показать дубли
              </button>
            )}
            <button type="button" className="btn btn--primary" data-testid="import-close" data-autofocus onClick={onClose}>
              Готово
            </button>
          </>
        }
      >
        <ResultView result={result} />
      </Dialog>
    )
  }

  return (
    <Dialog
      title="Загрузка выписки"
      subtitle="Выгрузите выписку из интернет-банка в формате 1С и выберите файл."
      wide
      onClose={onClose}
      busy={uploading}
      hideClose={uploading}
      dirty={false}
      closeRef={closeRef}
      testId="import-dialog"
      footer={
        uploading ? (
          <button type="button" className="btn" onClick={() => handle.current?.abort()}>
            Прервать
          </button>
        ) : (
          <>
            <button type="button" className="btn" onClick={() => closeRef.current?.()} data-testid="import-close">
              Отмена
            </button>
            <button type="submit" form="import-form" className="btn btn--primary" data-testid="import-submit">
              {blockError ? 'Повторить загрузку' : 'Загрузить'}
            </button>
          </>
        )
      }
    >
      <form id="import-form" noValidate onSubmit={submit}>
        {bankAccounts.length > 0 && (
          <Field label="Счёт" hint="Для какого счёта эта выписка">
            {(control) => (
              <select
                {...control}
                className="input"
                value={accountId}
                disabled={uploading}
                onChange={(event) => setPickedAccount(event.target.value)}
                data-testid="import-account"
              >
                {bankAccounts.length > 1 && <option value={FROM_FILE}>Определить по номеру счёта в файле</option>}
                {bankAccounts.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}
        <FileDrop
          file={file}
          onFile={chooseFile}
          error={fileError}
          disabled={uploading}
          accept=".txt,text/plain"
          formatHint="Формат 1С, файл .txt, до 10 МБ"
          inputTestId="import-file"
        />
        {uploading && (
          <>
            <ProgressBar percent={phase.percent} label={phase.percent === null ? 'Разбираем операции…' : 'Загружаем файл…'} />
            {slow && <p className="imp-hint">Большой файл, подождите ещё немного.</p>}
          </>
        )}
        {!uploading && <p className="imp-hint">Мы читаем суммы, даты и назначения платежей. Фамилии физических лиц не сохраняются.</p>}
        {blockError && <InlineAlert testId="import-error">{blockError}</InlineAlert>}
      </form>
    </Dialog>
  )
}
