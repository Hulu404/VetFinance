import type { AcquiringDay, AcquiringReconciliation } from '../../api/types'
import { formatDateShort, formatDayMonth, formatDayRangeLong } from '../../lib/dates'
import { formatMoney, pluralRu } from '../../lib/format'

export interface StatusView {
  pill: { text: string; variant: 'success' | 'danger' | 'warning' | 'neutral' }
  /** Small text under the plate (design/screens/acquiring.md, "Статусы"). */
  detail: string | null
}

/** "не хватает 1 240 ₽" / "зачислено на 300 ₽ больше". The amount is the module of the number from the API, nothing is computed. */
export function mismatchDetail(day: AcquiringDay): string | null {
  const discrepancy = day.discrepancy?.value
  if (discrepancy === undefined || discrepancy === 0) return null
  if (discrepancy < 0) {
    const base = `не хватает ${formatMoney(Math.abs(discrepancy))}`
    return day.credited?.value === 0 ? `${base}: зачисления нет` : base
  }
  return `зачислено на ${formatMoney(discrepancy)} больше`
}

export function statusView(day: AcquiringDay, coveredTo: string | null, referenceYear: number | undefined): StatusView {
  switch (day.status) {
    case 'matched':
      return { pill: { text: 'сошлось', variant: 'success' }, detail: null }
    case 'mismatch':
      return { pill: { text: 'расхождение', variant: 'danger' }, detail: mismatchDetail(day) }
    case 'waiting':
      return {
        pill: { text: 'ждём зачисления', variant: 'warning' },
        detail: day.expected_by ? `ожидаем до ${formatDateShort(day.expected_by, referenceYear)}` : null,
      }
    case 'no_statement':
      return {
        pill: { text: 'нет выписки', variant: 'warning' },
        detail: coveredTo ? `выписка загружена по ${formatDateShort(coveredTo, referenceYear)}` : null,
      }
    default:
      return { pill: { text: 'нет оплат картой', variant: 'neutral' }, detail: null }
  }
}

/** "Банк зачисляет карточные оплаты за 1–3 рабочих дня и удерживает комиссию. ..." */
export function settlementNote(settlement: AcquiringReconciliation['settlement_days']): string {
  const { min, max } = settlement
  const span = min === max ? `${max}` : `${min}–${max}`
  const noun = pluralRu(max, 'рабочий день', 'рабочих дня', 'рабочих дней')
  return `Банк зачисляет карточные оплаты за ${span} ${noun} и удерживает комиссию. Одно зачисление может закрывать несколько дней подряд.`
}

export function reviewedToast(day: AcquiringDay): string {
  if (day.date_from === day.date_to) return `День ${formatDayMonth(day.date_from)} отмечен проверенным.`
  return `Дни ${formatDayRangeLong(day.date_from, day.date_to)} отмечены проверенными.`
}
