import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isApiError } from '../../api/errors'
import { useConnections } from '../../api/queries'
import { ConnectionStatus } from '../../components/ConnectionStatus'
import { LoadErrorCard } from '../../components/StateBlocks'
import { formatDayMonth } from '../../lib/dates'
import { ImportDialog } from '../transactions/ImportDialog'
import { bankView } from './connectionView'

export function BankSection() {
  const connections = useConnections()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState<{ accountId?: string } | null>(null)
  const bank = connections.data?.items.find((item) => item.type === 'bank')

  if (connections.isPending) {
    return (
      <section className="set-card" aria-busy="true" aria-labelledby="bank-title">
        <h2 id="bank-title" className="sr-only">
          Банк
        </h2>
        <p className="sr-only" role="status">Загружаем подключения</p>
        <ConnectionStatus name="Банк" meta="выписка 1С, загрузка файлом" tone="off" statusText="" loading />
        <div className="set-skel" aria-hidden="true" />
      </section>
    )
  }
  if (connections.isError && !bank) {
    return (
      <LoadErrorCard
        testId="bank-load-error"
        title="Не получилось загрузить подключения"
        network={isApiError(connections.error) && connections.error.kind === 'network'}
        retrying={connections.isFetching}
        onRetry={() => void connections.refetch()}
      />
    )
  }
  if (!bank) return null

  const view = bankView(bank)
  const accounts = bank.bank?.accounts ?? []

  return (
    <>
      <section className="set-card" aria-labelledby="bank-title" data-testid="bank-card">
        <h2 id="bank-title" className="sr-only">
          Банк
        </h2>
        <ConnectionStatus
          testId="bank-status"
          name="Банк"
          meta="выписка 1С, загрузка файлом"
          tone={view.tone}
          statusText={view.statusText}
          pill={view.pill}
        />
        {accounts.length === 0 ? (
          <p className="set-text">Нет банковских счетов. Счёт пока заводит команда ВетФинанс.</p>
        ) : (
          <ul className="bank-accounts">
            {accounts.map((item) => (
              <li key={item.account.id} className="bank-accounts__row" data-testid="bank-account">
                <div>
                  <p className="bank-accounts__name">{item.account.name}</p>
                  <p className="bank-accounts__meta">
                    {item.last_statement_to ? `выписка по ${formatDayMonth(item.last_statement_to)}` : 'выписок ещё не было'}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn--sm"
                  aria-label={`Загрузить выписку для счёта ${item.account.name}`}
                  onClick={() => setDialog({ accountId: item.account.id })}
                >
                  Загрузить
                </button>
              </li>
            ))}
          </ul>
        )}
        {accounts.length > 0 && (
          <div className="set-actions">
            <button type="button" className="btn btn--primary" data-testid="bank-import" onClick={() => setDialog({})}>
              Загрузить выписку
            </button>
          </div>
        )}
        <p className="set-note">
          Подойдёт выгрузка в формате 1С из любого банка. Подключение банка напрямую появится позже.
        </p>
      </section>
      {dialog && (
        <ImportDialog
          accountId={dialog.accountId}
          onClose={() => setDialog(null)}
          onOpenTab={(tab) => navigate(`/transactions?tab=${tab}`)}
        />
      )}
    </>
  )
}
