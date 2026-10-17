import { KpiCard } from '../../components/KpiCard'
import { WEEKDAY_HEADERS } from '../../lib/planning'
import type { CalendarView } from './useCalendarParams'

const GRID_CELLS = 28
const LIST_ROWS = 6

/** What stands in place of the calendar while it loads: three cards and a grid, or a chart and rows. */
export function CalendarSkeleton({ view }: { view: CalendarView }) {
  return (
    <div data-testid="calendar-loading">
      <p className="sr-only" role="status">
        Загружаем календарь
      </p>
      <ul className="kpi-grid kpi-grid--plan" aria-hidden="true">
        {['📥', '📤', '📉'].map((emoji) => (
          <li key={emoji}>
            <KpiCard label="" emoji={emoji} state="loading" />
          </li>
        ))}
      </ul>
      {view === 'month' ? (
        <div className="cal-skeleton" aria-hidden="true">
          <div className="cal-skeleton__head">
            {WEEKDAY_HEADERS.map((name) => (
              <span key={name}>{name}</span>
            ))}
          </div>
          <div className="cal-skeleton__grid">
            {Array.from({ length: GRID_CELLS }, (_, index) => (
              <span key={index} className="cal-skeleton__cell" />
            ))}
          </div>
        </div>
      ) : (
        <div aria-hidden="true">
          <div className="cal-skeleton__chart" />
          {Array.from({ length: LIST_ROWS }, (_, index) => (
            <div key={index} className="cal-skeleton__row" />
          ))}
        </div>
      )}
    </div>
  )
}
