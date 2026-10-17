import { useId, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Advice, AdviceSeverity } from '../api/types'
import { Pill, type PillVariant } from './Pill'
import './AdviceCard.css'

const SEVERITY: Record<AdviceSeverity, { variant: PillVariant; label: string }> = {
  alert: { variant: 'danger', label: 'срочно' },
  warning: { variant: 'warning', label: 'внимание' },
  good: { variant: 'success', label: 'хорошо' },
}

/** What the card needs of an advice. The calendar alert has the same shape with a text made of two parts. */
export type AdviceCardData = Omit<Advice, 'text' | 'link'> & { text: ReactNode; link?: Advice['link'] }

export interface AdviceTestIds {
  card: string
  title: string
  text: string
  why: string
  panel: string
}

const ADVICE_TEST_IDS: AdviceTestIds = {
  card: 'advice-card',
  title: 'advice-title',
  text: 'advice-text',
  why: 'advice-why',
  panel: 'advice-why-panel',
}

interface AdviceCardProps {
  advice: AdviceCardData
  open: boolean
  onToggle: () => void
  /** Test ids of another screen (the calendar alert); the dashboard ones by default. */
  testIds?: AdviceTestIds
  /** Extra `data-*` attributes of the card (the calendar alert: date, id). */
  attributes?: Record<`data-${string}`, string>
}

/** The address of the "Открыть календарь" button of the `cash_gap` advice: the path of the API and the day to open. */
function calendarLinkTarget(link: NonNullable<Advice['link']>): string {
  return link.date ? `${link.path}?date=${encodeURIComponent(link.date)}` : link.path
}

/** A conclusion of the service and the "Почему?" button that opens how it was reached (design/components.md, section 17). */
export function AdviceCard({ advice, open, onToggle, testIds = ADVICE_TEST_IDS, attributes }: AdviceCardProps) {
  const panelId = useId()
  const labelId = useId()
  const severity = SEVERITY[advice.severity]
  return (
    <li
      className={`advice advice--${advice.severity}`}
      data-testid={testIds.card}
      data-advice-id={testIds === ADVICE_TEST_IDS ? advice.id : undefined}
      data-severity={advice.severity}
      {...attributes}
    >
      <div className="advice__head">
        <div className="advice__main">
          <span className="advice__icon" aria-hidden="true">
            {advice.icon}
          </span>
          <div className="advice__body">
            <span className="advice__severity" data-testid="advice-severity">
              <Pill variant={severity.variant}>{severity.label}</Pill>
            </span>
            <h3 className="advice__title" data-testid={testIds.title}>
              {advice.title}
            </h3>
            <p className="advice__text" data-testid={testIds === ADVICE_TEST_IDS ? undefined : testIds.text}>
              {advice.text}
            </p>
            {advice.id === 'cash_gap' && advice.link && (
              <Link className="btn btn--text advice__link" to={calendarLinkTarget(advice.link)} data-testid="advice-calendar-link">
                Открыть календарь
              </Link>
            )}
          </div>
        </div>
        <button
          type="button"
          className="advice__why"
          aria-expanded={open}
          aria-controls={panelId}
          data-testid={testIds.why}
          onClick={onToggle}
        >
          {open ? 'Свернуть' : 'Почему?'}
        </button>
      </div>
      {open && (
        <div id={panelId} className="advice__panel" role="region" aria-labelledby={labelId} data-testid={testIds.panel}>
          <div data-testid="advice-why-body">
            <div id={labelId} className="advice__panel-label">
              Разбор
            </div>
            <p>{advice.why.summary}</p>
            <ol className="advice__steps" data-testid="advice-why-steps">
              {advice.why.steps.map((step, index) => (
                <li key={`${index}-${step}`} data-testid="advice-why-step">
                  {step}
                </li>
              ))}
            </ol>
            <p className="advice__sources" data-testid="advice-why-sources">
              Источник: {advice.why.sources.join('; ')}
            </p>
          </div>
        </div>
      )}
    </li>
  )
}
