import { Link } from 'react-router-dom'
import type { CalendarPartialReason } from '../../api/types'
import { Banner } from '../../components/Banner'
import { pluralDays } from '../../lib/format'
import { IMPORT_ROUTE } from '../reports/ReportBlocks'

interface CalendarPartialProps {
  reasons: CalendarPartialReason[]
  historyDays: number
  onAddPayment: () => void
}

/** Why the calendar may miss payments: one strip, a line per reason, in the order of the answer (design/screens/calendar.md). */
export function CalendarPartial({ reasons, historyDays, onAddPayment }: CalendarPartialProps) {
  if (reasons.length === 0) return null
  return (
    <Banner variant="warning" testId="calendar-partial-banner" attributes={{ 'data-reasons': reasons.join(',') }}>
      <span className="cal-reasons">
        {reasons.map((reason) => (
          <span key={reason} className="cal-reasons__line">
            {reason === 'short_history' && (
              <>
                Банковской истории пока {historyDays} {pluralDays(historyDays)}: регулярным мы считаем платёж, который был в каждом из
                трёх последних месяцев, а выручку усредняем по 12 неделям. Часть платежей может не попасть в календарь — добавьте их
                сами.{' '}
                <button type="button" className="banner__action" onClick={onAddPayment}>
                  Добавить платёж
                </button>
              </>
            )}
            {reason === 'obligations_missing' && (
              <>
                В выписке есть платежи по кредиту или лизингу, но в «Обязательствах» их нет: календарь их не видит.{' '}
                <Link className="banner__action" to="/planning/obligations">
                  Обязательства
                </Link>
              </>
            )}
            {reason === 'no_bank' && (
              <>
                Выписки банка нет: в календаре только обязательства и платежи, внесённые вручную.{' '}
                <Link className="banner__action" to={IMPORT_ROUTE}>
                  Загрузить выписку
                </Link>
              </>
            )}
          </span>
        ))}
      </span>
    </Banner>
  )
}
