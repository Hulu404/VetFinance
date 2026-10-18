import { Link } from 'react-router-dom'
import type { EfficiencyReport } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { formatFigure } from '../../lib/format'

const EXPLANATION = 'Столько стоит один рабочий час: аренда, оклады, коммуналка и платежи по обязательствам, разделённые на часы работы.'
const EXPLANATION_DOCTORS = 'Столько стоит один час приёма врача: аренда, оклады, коммуналка и платежи по обязательствам, разделённые на часы приёма.'

export function HourCostCard({ report }: { report: EfficiencyReport }) {
  const doctors = report.load_by === 'doctors'
  const title = doctors ? 'Стоимость часа приёма' : 'Стоимость часа работы клиники'
  const { hour_cost: cost, hour_margin: margin } = report
  const reportLink = `/reports/pnl?month=${report.month}`
  return (
    <section className="eff-card" aria-labelledby="eff-cost-title" data-testid="efficiency-cost">
      <h2 id="eff-cost-title" className="eff-card__title">
        {title}
      </h2>
      {cost ? (
        <>
          <p className="eff-cost__value" data-testid="efficiency-hour-cost" data-figure="hour_cost">
            <FigureButton figure={cost} title={title} />
          </p>
          <p className="eff-cost__text">{doctors ? EXPLANATION_DOCTORS : EXPLANATION}</p>
        </>
      ) : (
        <>
          <p className="eff-cost__value" data-testid="efficiency-hour-cost">
            —
          </p>
          <p className="eff-cost__text">Нужны рабочие часы клиники</p>
        </>
      )}
      {report.hour_cost_parts.length > 0 && (
        <dl className="eff-parts">
          {report.hour_cost_parts.map((part) => (
            <div key={part.key} className="eff-parts__row" data-testid="efficiency-part" data-key={part.key} data-figure={`hour_cost_parts.${part.key}`}>
              <dt>{part.label}</dt>
              <dd>
                <FigureButton figure={part.figure} title={part.label} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      <div className="eff-margin">
        <p className="eff-margin__row">
          <span>Занятый час приносит</span>
          {margin ? (
            <span data-testid="efficiency-hour-margin" data-figure="hour_margin">
              <FigureButton figure={margin} title="Занятый час приносит" spokenValue={formatFigure(margin)} />
            </span>
          ) : (
            <span data-testid="efficiency-hour-margin">—</span>
          )}
        </p>
        {margin && <p className="eff-cost__text">после лекарств, процентов врачам и комиссий</p>}
      </div>
      {report.hour_cost_parts.some((part) => part.key === 'obligations') && (
        <Link className="eff-cost__link" to={reportLink}>
          Открыть отчёт «Прибыль и убытки»
        </Link>
      )}
    </section>
  )
}
