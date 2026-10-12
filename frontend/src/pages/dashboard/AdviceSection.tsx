import { useState } from 'react'
import type { Advice } from '../../api/types'
import { AdviceCard } from '../../components/AdviceCard'
import { DashEmpty } from './DashEmpty'

/** Below this many days of history the service builds no advice (decision of the product owner, handoff 2026-10-12). */
export const MIN_HISTORY_POINTS = 7

interface AdviceSectionProps {
  /** `undefined` for an old response without advice: the block is not drawn. */
  advice: Advice[] | undefined
  /** Number of days in `balance_trend`: a short history explains an empty list. */
  historyDays?: number
}

function EmptyAdvice({ fewData }: { fewData: boolean }) {
  if (fewData) {
    return (
      <DashEmpty
        testId="advice-empty"
        icon="📈"
        title="Пока мало данных"
        text="Советы появятся, когда накопится хотя бы неделя данных."
      />
    )
  }
  return (
    <DashEmpty
      testId="advice-empty"
      icon="📈"
      title="Пока всё в порядке"
      text="Заметных отклонений нет. Совет появится, если что-то выйдет из нормы."
    />
  )
}

/** "Советы · N": order and count come from the API; one "Почему?" is open at a time. */
export function AdviceSection({ advice, historyDays }: AdviceSectionProps) {
  const [openId, setOpenId] = useState<string | null>(null)
  if (!advice) return null
  const fewData = historyDays !== undefined && historyDays < MIN_HISTORY_POINTS

  return (
    <section aria-labelledby="advice-caption" data-testid="advice-section">
      <h2 id="advice-caption" className="dash-caption" data-no-tip>
        {advice.length > 0 ? `Советы · ${advice.length}` : 'Советы'}
      </h2>
      {advice.length === 0 ? (
        <EmptyAdvice fewData={fewData} />
      ) : (
        <ul className="advice-list" data-testid="advice-list">
          {advice.map((item) => (
            <AdviceCard
              key={item.id}
              advice={item}
              open={openId === item.id}
              onToggle={() => setOpenId((current) => (current === item.id ? null : item.id))}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
