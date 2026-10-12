import { useEffect, useRef, useState, type FormEvent } from 'react'
import { isApiError } from '../../api/errors'
import { useSaveVetmanager, useSyncConnection } from '../../api/mutations'
import { SYNC_POLL_LIMIT_MS, useClinic, useConnections, useDashboard } from '../../api/queries'
import type { Connection } from '../../api/types'
import { Banner } from '../../components/Banner'
import { ConnectionStatus } from '../../components/ConnectionStatus'
import { Field } from '../../components/Field'
import { LoadErrorCard } from '../../components/StateBlocks'
import { useToast } from '../../components/Toast'
import { formatMomentComma } from '../../lib/dates'
import { syncErrorFull } from '../../lib/syncText'
import { SyncRunsCard } from './SyncRunsCard'
import { vetmanagerView } from './connectionView'
import { normalizeAddress, serverVetmanagerErrors, validateVetmanager, type VetmanagerErrors } from './vetmanagerForm'
import { useSyncToasts } from './useSyncToasts'

const KEY_MASK = '••••••••••••'

function Skeleton() {
  return (
    <section className="set-card" aria-busy="true" aria-labelledby="vm-title">
      <h2 id="vm-title" className="sr-only">
        Ветменеджер
      </h2>
      <p className="sr-only" role="status">Загружаем подключения</p>
      <ConnectionStatus name="Ветменеджер" meta="визиты, продажи и услуги" tone="off" statusText="" loading />
      <div className="set-skel" aria-hidden="true" />
      <div className="set-skel" aria-hidden="true" />
    </section>
  )
}

function WithoutVetmanager() {
  return (
    <section className="set-card set-card--plain" aria-labelledby="without-title">
      <h3 id="without-title" className="klabel">
        Работа без Ветменеджера
      </h3>
      <p className="set-text">
        Сервис работает и без него. Операции можно загружать выпиской из банка и вносить вручную. Не будет только данных о
        визитах, продажах и услугах из Ветменеджера.
      </p>
    </section>
  )
}

function spokenKey(hint: string): string {
  return `Ключ скрыт, последние четыре знака ${hint.split('').join(' ')}`
}

interface FormProps {
  connection: Connection
  asOf: string | undefined
  timeZone: string | undefined
  syncing: boolean
}

function VetmanagerForm({ connection, asOf, timeZone, syncing }: FormProps) {
  const toast = useToast()
  const save = useSaveVetmanager()
  const sync = useSyncConnection()
  const [address, setAddress] = useState(connection.address ?? '')
  const [key, setKey] = useState('')
  const [replacing, setReplacing] = useState(false)
  const [errors, setErrors] = useState<VetmanagerErrors>({})
  const [general, setGeneral] = useState<string | null>(null)
  const keyRef = useRef<HTMLInputElement | null>(null)
  const addressRef = useRef<HTMLInputElement | null>(null)

  const connected = connection.connected
  const view = vetmanagerView(connection, asOf, timeZone)
  const maskShown = connected && !replacing
  const run = connection.last_run
  const failedRun = run?.status === 'failed' ? run : null
  const busy = save.isPending

  useEffect(() => {
    if (replacing) keyRef.current?.focus()
  }, [replacing])

  const startReplacing = () => {
    setKey('')
    setReplacing(true)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setGeneral(null)
    const clean = normalizeAddress(address)
    const found = validateVetmanager(clean, key, !connected)
    setErrors(found)
    if (found.address || found.key) {
      const target = found.address ? addressRef : keyRef
      target.current?.focus()
      return
    }
    save.mutate(
      { address: clean, ...(key.trim() !== '' ? { key: key.trim() } : {}) },
      {
        onSuccess: () => {
          setKey('')
          setReplacing(false)
          setErrors({})
          toast.show({
            message: connected
              ? 'Подключение сохранено.'
              : 'Ветменеджер подключён. Начали загружать данные, это может занять несколько минут.',
          })
        },
        onError: (error) => {
          if (isApiError(error) && error.kind === 'validation' && Object.keys(error.fields).length > 0) {
            const mapped = serverVetmanagerErrors(error.fields, clean)
            setErrors(mapped)
            const target = mapped.address ? addressRef : keyRef
            target.current?.focus()
            return
          }
          setGeneral(
            isApiError(error) && error.kind === 'network'
              ? 'Нет связи с сервером. Проверьте интернет и повторите'
              : 'Не получилось сохранить подключение. Попробуйте ещё раз',
          )
        },
      },
    )
  }

  const startSync = () => {
    sync.mutate(connection.id, {
      onError: (error) => {
        if (isApiError(error) && error.kind === 'conflict') {
          toast.show({ message: 'Синхронизация уже идёт. Подождите, пока закончится.' })
        } else if (isApiError(error) && error.kind === 'rate_limited') {
          toast.show({ kind: 'error', message: 'Синхронизировать можно не чаще раза в 5 минут. Попробуйте позже.' })
        } else {
          toast.show({ kind: 'error', message: 'Не получилось запустить синхронизацию. Проверьте интернет и повторите.' })
        }
      },
    })
  }

  const syncBusy = syncing || sync.isPending
  const lastSuccess = connection.last_success_at
    ? `Показаны данные на ${formatMomentComma(connection.last_success_at, asOf, timeZone)}.`
    : 'Данные пока не загружались.'

  return (
    <>
      {connection.data_stale && connected && view.tone === 'stale' && (
        <Banner variant="warning" testId="vm-stale">
          Ветменеджер давно не обновлялся. Нажмите «Синхронизировать» или проверьте ключ.
        </Banner>
      )}
      <section className="set-card" aria-labelledby="vm-title" data-testid="vm-card">
        <h2 id="vm-title" className="sr-only">
          Ветменеджер
        </h2>
        <ConnectionStatus
          testId="vm-status"
          name="Ветменеджер"
          meta="визиты, продажи и услуги"
          tone={view.tone}
          statusText={view.statusText}
          pill={view.pill}
        />
        {syncing && <LongSync />}
        {failedRun && (
          <div className="set-reason" role="alert" data-testid="vm-error">
            <p>{syncErrorFull(failedRun.error_code)}.</p>
            <p>{lastSuccess}</p>
            {failedRun.error_code === 'invalid_key' && !replacing && (
              <button type="button" className="btn btn--sm" onClick={startReplacing}>
                Заменить ключ
              </button>
            )}
          </div>
        )}
        {run?.status === 'partial' && <p className="set-hint">Часть данных не загрузилась. Остальное уже в учёте</p>}

        <form noValidate onSubmit={submit} className="set-form">
          <div className="set-line">
            <Field label="Адрес системы" error={errors.address} hint="Например, aibolit.vetmanager.ru">
              {(control) => (
                <input
                  {...control}
                  ref={addressRef}
                  type="text"
                  inputMode="url"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  autoComplete="off"
                  className="input"
                  value={address}
                  disabled={busy}
                  onChange={(event) => {
                    setAddress(event.target.value)
                    setErrors((current) => ({ ...current, address: undefined }))
                  }}
                />
              )}
            </Field>
          </div>
          <div className="set-line">
            <Field
              label="Ключ доступа"
              error={errors.key}
              hint={connected ? undefined : 'Вставьте ключ из Ветменеджера'}
            >
              {(control) => (
                <div className="set-key">
                  {maskShown ? (
                    <input
                      id={control.id}
                      type="text"
                      className="input"
                      value={`${KEY_MASK}${connection.key_hint ?? ''}`}
                      disabled
                      readOnly
                      aria-label={spokenKey(connection.key_hint ?? '')}
                    />
                  ) : (
                    <input
                      {...control}
                      ref={keyRef}
                      type="password"
                      autoComplete="off"
                      autoCapitalize="none"
                      spellCheck={false}
                      className="input"
                      value={key}
                      disabled={busy}
                      onChange={(event) => {
                        setKey(event.target.value)
                        setErrors((current) => ({ ...current, key: undefined }))
                      }}
                    />
                  )}
                  {connected &&
                    (replacing ? (
                      <button
                        type="button"
                        className="btn btn--text"
                        disabled={busy}
                        onClick={() => {
                          setReplacing(false)
                          setKey('')
                          setErrors((current) => ({ ...current, key: undefined }))
                        }}
                      >
                        Не менять
                      </button>
                    ) : (
                      <button type="button" className="btn" disabled={busy} onClick={startReplacing}>
                        Заменить ключ
                      </button>
                    ))}
                </div>
              )}
            </Field>
          </div>
          <div className="set-line set-line--static">
            <span className="fld__label">Обновление</span>
            <span className="set-static">
              {connection.schedule ? `Каждую ночь в ${connection.schedule.time}` : 'Расписание появится после подключения'}
            </span>
          </div>
          {general && (
            <p className="inline-alert" role="alert" data-testid="vm-form-error">
              {general}
            </p>
          )}
          <div className="set-actions">
            <button type="submit" className="btn btn--primary" disabled={busy} aria-busy={busy || undefined} data-testid="vm-save">
              {busy ? 'Сохраняем…' : connected ? 'Сохранить' : 'Подключить'}
            </button>
            {connected && (
              <button
                type="button"
                className="btn"
                disabled={syncBusy}
                aria-busy={syncBusy || undefined}
                data-testid="vm-sync"
                onClick={startSync}
              >
                {syncBusy ? 'Синхронизируем…' : 'Синхронизировать'}
              </button>
            )}
          </div>
          <p className="set-note">
            Ключ выдаётся в настройках Ветменеджера, раздел «Интеграции». Мы только читаем данные и ничего в них не
            меняем. Фамилии владельцев животных не сохраняются.
          </p>
        </form>
      </section>
    </>
  )
}

function LongSync() {
  const [long, setLong] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setLong(true), SYNC_POLL_LIMIT_MS)
    return () => window.clearTimeout(timer)
  }, [])
  return long ? <p className="set-hint">Идёт дольше обычного. Обновите страницу чуть позже.</p> : null
}

export function VetmanagerSection() {
  const connections = useConnections({ pollWhileRunning: true })
  const dashboard = useDashboard()
  const clinic = useClinic()
  const vetmanager = connections.data?.items.find((item) => item.type === 'vetmanager')
  useSyncToasts(vetmanager)

  const asOf = dashboard.data?.as_of
  const timeZone = clinic.data?.timezone
  const syncing = vetmanager?.last_run?.status === 'running'

  if (connections.isPending) return <Skeleton />
  if (connections.isError && !vetmanager) {
    return (
      <LoadErrorCard
        testId="vm-load-error"
        title="Не получилось загрузить подключения"
        network={isApiError(connections.error) && connections.error.kind === 'network'}
        retrying={connections.isFetching}
        onRetry={() => void connections.refetch()}
      />
    )
  }
  if (!vetmanager) return null

  return (
    <>
      <VetmanagerForm
        // A fresh form for a different connection state: the saved address and key hint come from the API.
        key={`${vetmanager.connected}-${vetmanager.address ?? ''}`}
        connection={vetmanager}
        asOf={asOf}
        timeZone={timeZone}
        syncing={syncing}
      />
      <SyncRunsCard
        runs={vetmanager.runs}
        loading={false}
        failed={false}
        onRetry={() => void connections.refetch()}
        asOf={asOf}
        timeZone={timeZone}
      />
      {!vetmanager.connected && <WithoutVetmanager />}
    </>
  )
}
