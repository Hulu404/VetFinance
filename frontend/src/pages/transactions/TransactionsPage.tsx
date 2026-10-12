import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useUpdateCategory } from '../../api/mutations'
import { invalidateAfterOperationChange, useClinic, useDashboard, useTransactionCounts } from '../../api/queries'
import type { Dashboard, Transaction } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { Pill } from '../../components/Pill'
import { TabPanel, Tabs, type TabDef } from '../../components/Tabs'
import { useToast } from '../../components/Toast'
import { formatAsOfDate, formatClockTime, formatMoney } from '../../lib/format'
import { isValidMonth, monthOf, yearOf } from '../../lib/dates'
import { NARROW_LIST_QUERY, useMediaQuery } from '../../lib/useMediaQuery'
import { AcquiringPanel, AcquiringSummary } from './AcquiringPanel'
import { CategoryDialog, savedMessage } from './CategoryDialog'
import { DuplicatesPanel } from './DuplicatesPanel'
import { ImportDialog } from './ImportDialog'
import { ManualOperationDialog } from './ManualOperationDialog'
import { MonthSwitch } from './MonthSwitch'
import { RulesPanel } from './RulesPanel'
import { StatusBanners } from './StatusBanners'
import { SummaryCards } from './SummaryCards'
import { TxPanel } from './TxPanel'
import './TransactionsPage.css'

type TabId = 'all' | 'check' | 'duplicates' | 'rules' | 'acquiring'

const TAB_IDS: readonly TabId[] = ['all', 'check', 'duplicates', 'rules', 'acquiring']
const PANEL_PREFIX = 'tx'

function tabFrom(value: string | null): TabId {
  return TAB_IDS.find((id) => id === value) ?? 'all'
}

function subtitleFor(data: Dashboard, timeZone: string | undefined) {
  const date = formatAsOfDate(data.as_of)
  const freshness = data.data_as_of
    ? `данные обновлены в ${formatClockTime(data.data_as_of, timeZone)}`
    : 'данные ещё не загружались'
  return (
    <>
      <span>
        {date} · {freshness}
      </span>
      {data.data_stale && <Pill variant="warning">данные устарели</Pill>}
    </>
  )
}

export function TransactionsPage() {
  const [params, setParams] = useSearchParams()
  const dashboard = useDashboard()
  const clinic = useClinic()
  const counts = useTransactionCounts()
  const update = useUpdateCategory()
  const toast = useToast()
  const queryClient = useQueryClient()
  const narrow = useMediaQuery(NARROW_LIST_QUERY)
  const headingRef = useRef<HTMLHeadingElement | null>(null)

  const [editing, setEditing] = useState<Transaction | null>(null)
  const [manualOpen, setManualOpen] = useState(false)
  // "Загрузить выписку" on the dashboard leads here with ?import=1: the dialog opens at once, the parameter is dropped.
  const [importOpen, setImportOpen] = useState(() => params.get('import') === '1')

  const asOf = dashboard.data?.as_of
  const currentMonth = asOf ? monthOf(asOf) : null
  const monthParam = params.get('month')
  const month = isValidMonth(monthParam) ? monthParam : currentMonth
  const tab = tabFrom(params.get('tab'))
  const referenceYear = asOf ? yearOf(asOf) : undefined
  const highlight = params.get('rule')

  const importRequested = params.get('import') === '1'
  useEffect(() => {
    if (!importRequested) return
    const cleaned = new URLSearchParams(params)
    cleaned.delete('import')
    setParams(cleaned, { replace: true })
  }, [importRequested, params, setParams])

  const focusHeading = useCallback(() => headingRef.current?.focus(), [])

  const go = useCallback(
    (next: { tab?: TabId; month?: string; rule?: string }) => {
      const merged = new URLSearchParams(params)
      if (next.tab) {
        if (next.tab === 'all') merged.delete('tab')
        else merged.set('tab', next.tab)
        merged.delete('rule')
      }
      if (next.month) merged.set('month', next.month)
      if (next.rule) merged.set('rule', next.rule)
      setParams(merged, { replace: false })
    },
    [params, setParams],
  )

  const tabs: TabDef<TabId>[] = [
    { id: 'all', label: 'Все', count: counts.isPending ? 'loading' : (counts.data?.all ?? null) },
    { id: 'check', label: 'На проверку', count: counts.isPending ? 'loading' : (counts.data?.check ?? null) },
    { id: 'duplicates', label: 'Дубли', count: counts.isPending ? 'loading' : (counts.data?.duplicates ?? null) },
    { id: 'rules', label: 'Правила разнесения' },
    { id: 'acquiring', label: 'Сверка эквайринга' },
  ]

  const confirmSuggestion = (tx: Transaction) => {
    const suggestion = tx.suggestion
    if (!suggestion) return
    update.mutate(
      { id: tx.id, categoryId: suggestion.category.id, createRule: suggestion.reason === 'similar' },
      {
        onSuccess: (result) => {
          const text = savedMessage(result, suggestion.category.name)
          toast.show({
            message: text.message,
            action: result.rule ? { label: 'Посмотреть правило', onClick: () => go({ tab: 'rules', rule: result.rule?.id }) } : undefined,
          })
          focusHeading()
        },
        onError: () => toast.show({ kind: 'error', message: 'Не получилось сохранить статью. Операция осталась как была. Попробуйте ещё раз.' }),
      },
    )
  }

  const onSaved = (result: Parameters<typeof savedMessage>[0], categoryName: string) => {
    const text = savedMessage(result, categoryName)
    setEditing(null)
    toast.show({
      message: text.message,
      action: result.rule ? { label: 'Посмотреть правило', onClick: () => go({ tab: 'rules', rule: result.rule?.id }) } : undefined,
    })
  }

  const onCreated = (tx: Transaction) => {
    setManualOpen(false)
    const base = `Операция добавлена: ${tx.description}, ${formatMoney(tx.amount)}`
    if (tx.status === 'duplicate') {
      toast.show({
        message: `${base}. Похожая операция уже есть, она показана во вкладке «Дубли».`,
        action: { label: 'Открыть дубли', onClick: () => go({ tab: 'duplicates' }) },
      })
    } else if (tx.status === 'check') {
      toast.show({
        message: `${base}. Статьи нет, операция ждёт во вкладке «На проверку».`,
        action: { label: 'Открыть проверку', onClick: () => go({ tab: 'check' }) },
      })
    } else {
      toast.show({ message: `${base}.` })
    }
  }

  const openTab = (id: 'check' | 'duplicates') => go({ tab: id })

  return (
    <>
      <PageHeader
        title="Транзакции"
        balance
        subtitle={dashboard.data ? subtitleFor(dashboard.data, clinic.data?.timezone) : undefined}
        subtitleLoading={dashboard.isPending}
        actions={
          <>
            <button type="button" className="btn btn--primary" data-testid="manual-open" onClick={() => setManualOpen(true)}>
              + Операция
            </button>
            <button type="button" className="btn" data-testid="import-open" onClick={() => setImportOpen(true)}>
              Загрузить выписку
            </button>
          </>
        }
      />
      <StatusBanners />
      <MonthSwitch month={month} currentMonth={currentMonth} onChange={(next) => go({ month: next })} />
      {tab === 'acquiring' ? <AcquiringSummary month={month} /> : <SummaryCards month={month} />}
      <Tabs
        prefix={PANEL_PREFIX}
        label="Разделы транзакций"
        tabs={tabs}
        value={tab}
        onChange={(id) => go({ tab: id })}
      />
      <TabPanel prefix={PANEL_PREFIX} id={tab}>
        {(tab === 'all' || tab === 'check') && (
          <TxPanel
            tab={tab}
            month={month}
            referenceYear={referenceYear}
            narrow={narrow}
            busyId={update.isPending ? update.variables.id : null}
            headingRef={headingRef}
            onEdit={setEditing}
            onConfirm={confirmSuggestion}
            onOpenImport={() => setImportOpen(true)}
            onOpenManual={() => setManualOpen(true)}
          />
        )}
        {tab === 'duplicates' && <DuplicatesPanel referenceYear={referenceYear} narrow={narrow} headingRef={headingRef} />}
        {tab === 'rules' && <RulesPanel narrow={narrow} highlightId={highlight} headingRef={headingRef} />}
        {tab === 'acquiring' && (
          <AcquiringPanel
            month={month}
            referenceYear={referenceYear}
            narrow={narrow}
            headingRef={headingRef}
            onOpenImport={() => setImportOpen(true)}
          />
        )}
      </TabPanel>

      {editing && (
        <CategoryDialog
          tx={editing}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
          onRefresh={() => {
            setEditing(null)
            void invalidateAfterOperationChange(queryClient)
          }}
          fallbackFocus={focusHeading}
        />
      )}
      {manualOpen && <ManualOperationDialog asOf={asOf ?? ''} onClose={() => setManualOpen(false)} onCreated={onCreated} />}
      {importOpen && <ImportDialog onClose={() => setImportOpen(false)} onOpenTab={openTab} />}
    </>
  )
}
