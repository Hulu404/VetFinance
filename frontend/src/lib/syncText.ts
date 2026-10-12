import type { SyncErrorCode } from '../api/types'

/** Full phrases for the connections screen and toasts (design/screens/connections.md). The backend message is never shown. */
const FULL: Record<SyncErrorCode, string> = {
  invalid_key:
    'Ветменеджер не принял ключ. Проверьте ключ в настройках Ветменеджера, раздел «Интеграции», и замените его здесь',
  unreachable: 'Ветменеджер не отвечает. Попробуем снова по расписанию или нажмите «Синхронизировать»',
  rate_limited: 'Ветменеджер просит подождать. Попробуйте через несколько минут',
  unknown: 'Не получилось обновить данные. Это сбой на нашей стороне, ваши данные не пострадали. Попробуйте ещё раз',
}

/** Short phrases for the strip on the transactions screen and the runs table. */
const SHORT: Record<SyncErrorCode, string> = {
  invalid_key: 'ключ не подошёл',
  unreachable: 'Ветменеджер не отвечает',
  rate_limited: 'Ветменеджер просит подождать',
  unknown: 'сбой при обновлении',
}

export function syncErrorFull(code: SyncErrorCode | null | undefined): string {
  return FULL[code ?? 'unknown'] ?? FULL.unknown
}

export function syncErrorShort(code: SyncErrorCode | null | undefined): string {
  return SHORT[code ?? 'unknown'] ?? SHORT.unknown
}
