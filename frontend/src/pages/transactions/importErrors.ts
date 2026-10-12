import { isApiError } from '../../api/errors'

export const MAX_FILE_BYTES = 10 * 1024 * 1024

/** Checks the file before it leaves the browser: extension, size, emptiness. The content is checked by the backend. */
export function checkStatementFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.txt')) {
    return 'Нужен файл в формате 1С с расширением .txt. В интернет-банке он называется «Выгрузка для 1С»'
  }
  if (file.size === 0) return 'В файле нет операций. Проверьте период выписки'
  if (file.size > MAX_FILE_BYTES) return 'Файл больше 10 МБ. Выгрузите выписку за меньший период'
  return null
}

export interface ImportFailure {
  /** Shown under the file field, the file stays chosen. */
  fileError?: string
  /** Shown in the red block of the dialog. */
  blockError?: string
}

const UNREADABLE =
  'Не получилось прочитать файл. Нужна выписка в формате 1С. Если вы выгружали другой формат, выгрузите ещё раз'

/** Text of an upload failure by the kind of the error and `details.reason` (design/screens/transactions.md, "Ошибки"). */
export function importFailure(error: unknown): ImportFailure {
  if (!isApiError(error)) return { blockError: 'Не получилось обработать выписку. Это сбой на нашей стороне, в учёт ничего не попало. Попробуйте ещё раз' }
  switch (error.kind) {
    case 'network':
      return { blockError: 'Загрузка прервалась. Проверьте интернет и повторите: повторная загрузка ничего не задвоит' }
    case 'rate_limited':
      return { blockError: 'Выписки грузятся не чаще раза в минуту. Подождите немного и повторите' }
    case 'validation':
      return validationFailure(error.reason, error.details.account_tail)
    default:
      return { blockError: 'Не получилось обработать выписку. Это сбой на нашей стороне, в учёт ничего не попало. Попробуйте ещё раз' }
  }
}

function validationFailure(reason: string | null, tail: unknown): ImportFailure {
  switch (reason) {
    case 'empty':
      return { fileError: 'В файле нет операций. Проверьте период выписки' }
    case 'too_large':
      return { fileError: 'Файл больше 10 МБ. Выгрузите выписку за меньший период' }
    case 'account_mismatch': {
      const digits = typeof tail === 'string' && tail ? ` (…${tail})` : ''
      return { blockError: `В выписке другой расчётный счёт${digits}. Выберите этот счёт в списке или загрузите другой файл` }
    }
    default:
      return { blockError: UNREADABLE }
  }
}
