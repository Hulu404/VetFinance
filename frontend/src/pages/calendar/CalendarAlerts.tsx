import { useState } from 'react'
import type { CalendarAlert } from '../../api/types'
import { AdviceCard, type AdviceTestIds } from '../../components/AdviceCard'

const ALERT_TEST_IDS: AdviceTestIds = {
  card: 'calendar-alert',
  title: 'calendar-alert-title',
  text: 'calendar-alert-text',
  why: 'calendar-alert-why',
  panel: 'calendar-alert-why-panel',
}

/**
 * The cash-gap alerts over the calendar, one card per run of red days. The text of the card is the text of the alert and the
 * sentence of the suggested move; the sentence is marked, so that a full move and a partial one can be told apart.
 */
export function CalendarAlerts({ alerts }: { alerts: CalendarAlert[] }) {
  const [openId, setOpenId] = useState<string | null>(null)
  if (alerts.length === 0) return null
  return (
    <ul className="advice-list" aria-label="Оповещения о кассовом разрыве" data-testid="calendar-alerts">
      {alerts.map((alert) => (
        <AdviceCard
          key={alert.id}
          advice={{
            ...alert,
            text: (
              <>
                {alert.text}
                {alert.suggestion && (
                  <>
                    {' '}
                    <span data-testid="calendar-alert-suggestion" data-closes-gap={String(alert.suggestion.closes_gap)}>
                      {alert.suggestion.text}
                    </span>
                  </>
                )}
              </>
            ),
          }}
          open={openId === alert.id}
          onToggle={() => setOpenId((current) => (current === alert.id ? null : alert.id))}
          testIds={ALERT_TEST_IDS}
          attributes={{
            'data-alert-id': alert.id,
            'data-date': alert.date,
            'data-date-to': alert.date_to,
          }}
        />
      ))}
    </ul>
  )
}
