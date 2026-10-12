import { describe, expect, it } from 'vitest'
import type { Connection } from '../../api/types'
import { bankView, vetmanagerView } from './connectionView'
import { normalizeAddress, serverVetmanagerErrors, validateVetmanager } from './vetmanagerForm'

function connection(patch: Partial<Connection> = {}): Connection {
  return {
    id: 'vetmanager',
    type: 'vetmanager',
    connected: true,
    address: 'aibolit.vetmanager.ru',
    key_hint: '4a7f',
    schedule: { kind: 'nightly', time: '04:00' },
    data_stale: false,
    last_success_at: '2026-09-09T04:12:00+03:00',
    last_run: null,
    runs: [],
    bank: null,
    ...patch,
  }
}

const run = { id: 'r', started_at: '2026-09-09T04:12:00+03:00', finished_at: null, error_code: null, counts: null }

describe('vetmanagerView', () => {
  const view = (patch: Partial<Connection>) => vetmanagerView(connection(patch), '2026-09-09', 'Europe/Moscow')

  it('is "не подключено" without a connection', () => {
    expect(view({ connected: false })).toMatchObject({ tone: 'off', statusText: 'не подключено', pill: null })
  })

  it('says "обновлено сегодня в 04:12" when all is fine', () => {
    expect(view({})).toMatchObject({ tone: 'ok', statusText: 'обновлено сегодня в 04:12', pill: null })
  })

  it('gives the running sync priority and names the first load', () => {
    expect(view({ last_run: { ...run, status: 'running' } }).statusText).toBe('синхронизация идёт…')
    expect(view({ last_success_at: null, last_run: { ...run, status: 'running' } }).statusText).toBe('загружаем историю…')
  })

  it('shows a plate with words for failed, partial and stale', () => {
    expect(view({ last_run: { ...run, status: 'failed' } }).pill?.text).toBe('ошибка синхронизации')
    expect(view({ last_run: { ...run, status: 'partial' } }).pill?.text).toBe('обновлено частично')
    const stale = view({ data_stale: true, last_success_at: '2026-09-08T04:12:00+03:00' })
    expect(stale.tone).toBe('stale')
    expect(stale.statusText).toBe('обновлено вчера в 04:12')
    expect(stale.pill?.text).toBe('данные устарели')
  })
})

describe('bankView', () => {
  const bank = (dates: (string | null)[], stale = false): Connection =>
    connection({
      id: 'bank',
      type: 'bank',
      data_stale: stale,
      bank: {
        accounts: dates.map((date, index) => ({ account: { id: `a${index}`, name: `Счёт ${index}` }, last_statement_to: date })),
      },
    })

  it('has no statements yet', () => {
    expect(bankView(bank([null, null]))).toMatchObject({ tone: 'off', statusText: 'выписок ещё не было' })
  })

  it('names the latest statement date among the accounts', () => {
    expect(bankView(bank(['2026-08-28', '2026-09-09'])).statusText).toBe('последняя выписка по 9 сентября')
  })

  it('marks stale statements with a plate', () => {
    expect(bankView(bank(['2026-08-28'], true)).pill?.text).toBe('данные устарели')
  })
})

describe('Vetmanager form', () => {
  it('cleans the address as the spec says and nothing more', () => {
    expect(normalizeAddress('  https://aibolit.vetmanager.ru/ ')).toBe('aibolit.vetmanager.ru')
    expect(normalizeAddress('HTTP://Clinic.VetManager.ru')).toBe('Clinic.VetManager.ru')
  })

  it('validates the address and the key', () => {
    expect(validateVetmanager('', 'k', true).address).toBe('Введите адрес вашего Ветменеджера')
    expect(validateVetmanager('nodot', 'k', true).address).toMatch(/Адрес выглядит неверно/)
    expect(validateVetmanager('a b.ru', 'k', true).address).toMatch(/Адрес выглядит неверно/)
    expect(validateVetmanager('aibolit.vetmanager.ru', '', true).key).toBe('Вставьте ключ из Ветменеджера')
    expect(validateVetmanager('aibolit.vetmanager.ru', '', false)).toEqual({})
  })

  it('puts the address into the server error text', () => {
    expect(serverVetmanagerErrors({ address: 'unreachable' }, 'aibolit.vetmanager.ru').address).toBe(
      'Не удалось связаться с aibolit.vetmanager.ru. Проверьте адрес',
    )
    expect(serverVetmanagerErrors({ key: 'invalid' }, 'x.ru').key).toBe('Ветменеджер не принял ключ. Проверьте ключ и адрес')
  })
})
