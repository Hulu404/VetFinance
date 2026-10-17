import { Link } from 'react-router-dom'
import type { CalendarReport } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { SAFE_SETTINGS_LINK } from '../../components/ForecastChart'

/** "Безопасный запас 60 000 ₽ · изменить в Настройках" under the grid and under the chart. */
export function SafeLine({ safe, safeSet }: { safe: CalendarReport['safe_balance']; safeSet: boolean }) {
  return (
    <p className="cal-safe" data-testid="calendar-safe">
      {safeSet ? (
        <>
          Безопасный запас{' '}
          <FigureButton figure={safe} title="Безопасный запас" figureKey="safe_balance" />
          {' · '}
          <Link to={SAFE_SETTINGS_LINK} data-testid="calendar-safe-link">
            изменить в Настройках
          </Link>
        </>
      ) : (
        <>
          Безопасный запас не задан{' · '}
          <Link to={SAFE_SETTINGS_LINK} data-testid="calendar-safe-link">
            задать в Настройках
          </Link>
        </>
      )}
    </p>
  )
}
