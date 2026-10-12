/** Strips the scheme and a trailing slash, trims spaces: the only changes made to the address before sending. */
export function normalizeAddress(input: string): string {
  return input
    .trim()
    .replace(/^https?:\/\//i, '')
    .replace(/\/+$/, '')
}

const ADDRESS_PATTERN = /^[a-z0-9-]+(\.[a-z0-9-]+)+(:\d+)?(\/[^\s]*)?$/i

export interface VetmanagerErrors {
  address?: string
  key?: string
}

export function validateVetmanager(address: string, key: string, keyRequired: boolean): VetmanagerErrors {
  const errors: VetmanagerErrors = {}
  if (address === '') errors.address = 'Введите адрес вашего Ветменеджера'
  else if (!ADDRESS_PATTERN.test(address)) errors.address = 'Адрес выглядит неверно. Пример: aibolit.vetmanager.ru'
  if (keyRequired && key.trim() === '') errors.key = 'Вставьте ключ из Ветменеджера'
  return errors
}

/** Texts of server reasons for the form fields (`error.details.fields`). */
export function serverVetmanagerErrors(fields: Record<string, string>, address: string): VetmanagerErrors {
  const errors: VetmanagerErrors = {}
  if (fields.address === 'unreachable') errors.address = `Не удалось связаться с ${address}. Проверьте адрес`
  else if (fields.address) errors.address = 'Адрес выглядит неверно. Пример: aibolit.vetmanager.ru'
  if (fields.key === 'invalid') errors.key = 'Ветменеджер не принял ключ. Проверьте ключ и адрес'
  else if (fields.key) errors.key = 'Вставьте ключ из Ветменеджера'
  return errors
}
