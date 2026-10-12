import { useId } from 'react'
import type { Advice, AdviceSeverity } from '../api/types'
import { Pill, type PillVariant } from './Pill'
import './AdviceCard.css'

const SEVERITY: Record<AdviceSeverity, { variant: PillVariant; label: string }> = {
  alert: { variant: 'danger', label: 'срочно' },
  warning: { variant: 'warning', label: 'внимание' },
  good: { variant: 'success', label: 'хорошо' },
}

interface AdviceCardProps {
  advice: Advice
  open: boolean
  onToggle: () => void
}

/** A conclusion of the service and the "Почему?" button that opens how it was reached (design/components.md, section 17). */
export function AdviceCard({ advice, open, onToggle }: AdviceCardProps) {
  const panelId = useId()
  const labelId = useId()
  const severity = SEVERITY[advice.severity]
  return (
    <li
      className={`advice advice--${advice.severity}`}
      data-testid="advice-card"
      data-advice-id={advice.id}
      data-severity={advice.severity}
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
            <h3 className="advice__title" data-testid="advice-title">
              {advice.title}
            </h3>
            <p className="advice__text">{advice.text}</p>
          </div>
        </div>
        <button
          type="button"
          className="advice__why"
          aria-expanded={open}
          aria-controls={panelId}
          data-testid="advice-why"
          onClick={onToggle}
        >
          {open ? 'Свернуть' : 'Почему?'}
        </button>
      </div>
      {open && (
        <div id={panelId} className="advice__panel" role="region" aria-labelledby={labelId} data-testid="advice-why-panel">
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
