import type { SyncRun } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { Pill, type PillVariant } from '../../components/Pill'
import { formatRunMoment } from '../../lib/dates'
import { syncErrorShort } from '../../lib/syncText'

const STATUS: Record<SyncRun['status'], { text: string; variant: PillVariant }> = {
  running: { text: 'идёт', variant: 'neutral' },
  success: { text: 'успешно', variant: 'success' },
  partial: { text: 'частично', variant: 'warning' },
  failed: { text: 'ошибка', variant: 'danger' },
}

interface SyncRunsCardProps {
  runs: SyncRun[] | undefined
  loading: boolean
  failed: boolean
  onRetry: () => void
  asOf: string | undefined
  timeZone: string | undefined
}

function Result({ run }: { run: SyncRun }) {
  const status = STATUS[run.status]
  return (
    <div className="runs__result">
      <Pill variant={status.variant}>{status.text}</Pill>
      {run.status === 'failed' && <span className="runs__reason">{syncErrorShort(run.error_code)}</span>}
    </div>
  )
}

function Loaded({ run }: { run: SyncRun }) {
  return run.counts ? <FigureButton figure={run.counts} title="Загружено" /> : <span aria-label="нет данных">—</span>
}

/** The last 5 runs of the synchronization (v6 `.klabel` card). */
export function SyncRunsCard({ runs, loading, failed, onRetry, asOf, timeZone }: SyncRunsCardProps) {
  let body
  if (failed) {
    body = (
      <p className="runs__msg">
        Не получилось загрузить список запусков.{' '}
        <button type="button" className="btn btn--text" onClick={onRetry}>
          Повторить
        </button>
      </p>
    )
  } else if (loading) {
    body = (
      <div aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <div key={index} className="runs__skeleton" />
        ))}
      </div>
    )
  } else if (!runs || runs.length === 0) {
    body = <p className="runs__msg">Запусков пока не было. Они появятся после подключения.</p>
  } else {
    body = (
      <>
        <table className="runs__table">
          <caption className="sr-only">Последние запуски синхронизации Ветменеджера</caption>
          <thead>
            <tr>
              <th scope="col">Когда</th>
              <th scope="col">Результат</th>
              <th scope="col" className="runs__num">
                Загружено
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} data-testid="sync-run">
                <td>{formatRunMoment(run.started_at, asOf, timeZone)}</td>
                <td>
                  <Result run={run} />
                </td>
                <td className="runs__num">
                  <Loaded run={run} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="runs__cards">
          {runs.map((run) => (
            <li key={run.id}>
              <div>
                <p>{formatRunMoment(run.started_at, asOf, timeZone)}</p>
                <Result run={run} />
              </div>
              <Loaded run={run} />
            </li>
          ))}
        </ul>
      </>
    )
  }
  return (
    <section className="set-card" aria-labelledby="runs-title">
      <h3 id="runs-title" className="klabel">
        Последние запуски
      </h3>
      {body}
    </section>
  )
}
