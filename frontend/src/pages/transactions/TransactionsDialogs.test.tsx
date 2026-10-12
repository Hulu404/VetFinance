import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { setMockScenario } from '../../mocks/scenario'
import { renderWithQuery } from '../../test/render'
import { TransactionsPage } from './TransactionsPage'

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  const { fakeUpload } = await import('../../test/uploadShim')
  return { ...actual, apiUpload: fakeUpload }
})

const STATEMENT = '1CClientBankExchange\nВерсияФормата=1.03\nКонецФайла\n'

function statement(name = 'statement.txt', body = STATEMENT) {
  return new File([body], name, { type: 'text/plain' })
}

function open(path = '/transactions') {
  return renderWithQuery(<TransactionsPage />, { toasts: true, path })
}

async function counter(name: string): Promise<number> {
  const text = (await screen.findByTestId(`import-${name}`)).textContent ?? ''
  return Number(text.replace(/\D/g, ''))
}

describe('Statement upload', () => {
  async function upload(user: ReturnType<typeof userEvent.setup>, file: File) {
    await user.click(await screen.findByTestId('import-open'))
    await user.upload(screen.getByTestId('import-file'), file)
    await user.click(screen.getByTestId('import-submit'))
  }

  it('uploads a file and shows the three counters; the privacy line is in the dialog', async () => {
    const user = userEvent.setup()
    open()
    await user.click(await screen.findByTestId('import-open'))
    expect(screen.getByText('Мы читаем суммы, даты и назначения платежей. Фамилии физических лиц не сохраняются.')).toBeInTheDocument()
    await user.upload(screen.getByTestId('import-file'), statement())
    await user.click(screen.getByTestId('import-submit'))

    expect(await screen.findByTestId('import-result')).toBeInTheDocument()
    expect(await counter('loaded')).toBe(148)
    expect(await counter('duplicates')).toBe(3)
    expect(await counter('to-check')).toBe(12)
    expect(screen.getByRole('button', { name: 'Показать на проверку' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Показать дубли' })).toBeInTheDocument()

    await user.click(screen.getByTestId('import-close'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('a repeated upload of the same file says nothing was added', async () => {
    const user = userEvent.setup()
    open()
    await upload(user, statement())
    await screen.findByTestId('import-result')
    await user.click(screen.getByTestId('import-close'))

    await upload(user, statement())
    expect(await screen.findByText('Эти операции уже были загружены, новых нет. Ничего не добавлено и не задвоено.')).toBeInTheDocument()
    expect(await counter('loaded')).toBe(0)
    expect(await counter('already-loaded')).toBe(29)
    expect(screen.queryByTestId('import-duplicates')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Показать дубли' })).not.toBeInTheDocument()
  })

  it('shows a readable message for a file that is not in 1C format and keeps the file', async () => {
    const user = userEvent.setup()
    open()
    await upload(user, statement('klient.txt', 'Клиент банка\nСекция=РасчСчет\n'))

    expect(await screen.findByTestId('import-error')).toHaveTextContent('формате 1С')
    expect(screen.getByText('klient.txt')).toBeInTheDocument()
    expect(screen.getByTestId('import-submit')).toHaveTextContent('Повторить загрузку')
  })

  it('checks the extension and the empty field before sending', async () => {
    const user = userEvent.setup({ applyAccept: false })
    open()
    await user.click(await screen.findByTestId('import-open'))
    await user.click(screen.getByTestId('import-submit'))
    expect(screen.getByText('Выберите файл выписки')).toBeInTheDocument()

    await user.upload(screen.getByTestId('import-file'), new File(['x'], 'statement.csv'))
    expect(screen.getByText(/Нужен файл в формате 1С с расширением \.txt/)).toBeInTheDocument()
  })

  it('names the account from the file when the statement belongs to another one', async () => {
    const user = userEvent.setup()
    open()
    await upload(user, statement('mismatch.txt'))
    expect(await screen.findByTestId('import-error')).toHaveTextContent('другой расчётный счёт (…7972)')
  })

  it('tells about the limit of uploads', async () => {
    const user = userEvent.setup()
    setMockScenario('ratelimit')
    open()
    await upload(user, statement())
    expect(await screen.findByTestId('import-error')).toHaveTextContent('не чаще раза в минуту')
  })

  it('reports skipped rows', async () => {
    const user = userEvent.setup()
    open()
    await upload(user, statement('skip.txt'))
    expect(await screen.findByText('Не удалось прочитать 2 строки файла, они пропущены.')).toBeInTheDocument()
  })
})

describe('Manual operation', () => {
  async function openDialog(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByTestId('manual-open'))
    return screen.findByRole('dialog', { name: 'Новая операция' })
  }

  it('shows the field errors from the table of the spec', async () => {
    const user = userEvent.setup()
    open()
    const dialog = await openDialog(user)
    await within(dialog).findByRole('option', { name: 'Расчётный счёт' })

    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText('Выберите счёт', { selector: 'p' })).toBeInTheDocument()
    expect(within(dialog).getByText('Введите сумму')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText('Сумма'), '12,345')
    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText('Не больше двух знаков после запятой')).toBeInTheDocument()

    await user.clear(within(dialog).getByLabelText('Сумма'))
    await user.type(within(dialog).getByLabelText('Сумма'), 'abc')
    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText('Введите сумму цифрами, например 5 400 или 5 400,50')).toBeInTheDocument()

    await user.clear(within(dialog).getByLabelText('Сумма'))
    await user.type(within(dialog).getByLabelText('Сумма'), '0')
    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText('Сумма должна быть больше нуля')).toBeInTheDocument()
  })

  it('rejects a date before the opening date of the account and after today', async () => {
    const user = userEvent.setup()
    open()
    const dialog = await openDialog(user)
    await within(dialog).findByRole('option', { name: 'Расчётный счёт' })
    await user.selectOptions(within(dialog).getByLabelText('Счёт'), 'A-bank')
    await user.type(within(dialog).getByLabelText('Сумма'), '640')

    const date = within(dialog).getByLabelText('Дата')
    await user.clear(date)
    await user.type(date, '2026-07-01')
    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText('Учёт по этому счёту идёт с 1 августа 2026. Выберите дату не раньше')).toBeInTheDocument()

    await user.clear(date)
    await user.type(date, '2026-09-20')
    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText(/Дата не может быть позже сегодняшней/)).toBeInTheDocument()
  })

  it('adds an expense, sends kopecks as an integer and tells what to do next', async () => {
    const user = userEvent.setup()
    const { queryClient } = open()
    const dialog = await openDialog(user)
    await within(dialog).findByRole('option', { name: 'Касса' })
    await user.selectOptions(within(dialog).getByLabelText('Счёт'), 'A-cash')
    await user.type(within(dialog).getByLabelText('Сумма'), '1 640,50')
    await user.type(within(dialog).getByLabelText(/Комментарий/), 'Такси за анализами')
    await user.click(within(dialog).getByTestId('manual-save'))

    expect(await screen.findByText(/Операция добавлена: Такси за анализами, −1 640,50 ₽\./)).toBeInTheDocument()
    expect(screen.getByText(/Статьи нет, операция ждёт во вкладке «На проверку»/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
  })

  it('keeps the comment limit', async () => {
    const user = userEvent.setup()
    open()
    const dialog = await openDialog(user)
    await within(dialog).findByRole('option', { name: 'Касса' })
    await user.selectOptions(within(dialog).getByLabelText('Счёт'), 'A-cash')
    await user.type(within(dialog).getByLabelText('Сумма'), '100')
    await user.click(within(dialog).getByLabelText(/Комментарий/))
    await user.paste('я'.repeat(201))
    await user.click(within(dialog).getByTestId('manual-save'))
    expect(within(dialog).getByText('Не больше 200 знаков')).toBeInTheDocument()
  })
})

describe('Reconciliation of acquiring', () => {
  it('shows the three cards, the note, the rows and a status in words for every state', async () => {
    open('/transactions?tab=acquiring')

    const table = await screen.findByTestId('acq-table')
    const rows = within(table).getAllByTestId('acq-row')
    expect(rows).toHaveLength(5)
    expect(screen.getByTestId('acq-card-payments')).toHaveTextContent('Оплачено картой')
    expect(screen.getByTestId('acq-card-payments')).toHaveTextContent('комиссия')
    expect(screen.getByTestId('acq-card-discrepancy')).toHaveTextContent('ждём ещё')
    expect(screen.getByText(/Банк зачисляет карточные оплаты за 1–3 рабочих дня/)).toBeInTheDocument()

    expect(rows[0]).toHaveTextContent('ждём зачисления')
    expect(rows[0]).toHaveTextContent('ожидаем до 14 сен')
    expect(rows[2]).toHaveTextContent('4–6 сен')
    expect(rows[2]).toHaveTextContent('расхождение')
    expect(rows[2]).toHaveTextContent('не хватает 1 240 ₽')
    expect(rows[3]).toHaveTextContent('сошлось')
    expect(rows[4]).toHaveTextContent('не хватает 29 430 ₽: зачисления нет')
    expect(screen.queryByText('Расхождений нет')).not.toBeInTheDocument()
  })

  it('opens the day, marks a mismatch as checked and shows the plate afterwards', async () => {
    const user = userEvent.setup()
    open('/transactions?tab=acquiring')
    const rows = await screen.findAllByTestId('acq-row')

    await user.click(within(rows[2] as HTMLElement).getByRole('button', { name: 'Подробнее за 4–6 сентября' }))
    const dialog = await screen.findByRole('dialog', { name: 'Сверка за 4–6 сентября' })
    expect(await within(dialog).findByText('Оплаты из Ветменеджера (4)')).toBeInTheDocument()
    expect(within(dialog).getByText('Зачисления банка (1)')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText(/Комментарий/), 'написали в банк')
    await user.click(within(dialog).getByTestId('acq-review'))
    expect(await screen.findByText('Дни 4–6 сентября отмечены проверенными.')).toBeInTheDocument()
    await waitFor(() => expect(within(screen.getAllByTestId('acq-row')[2] as HTMLElement).getByText('проверено')).toBeInTheDocument())
  })

  it('warns that the statement ends earlier than the sales', async () => {
    setMockScenario('nostatement')
    open('/transactions?tab=acquiring')

    const banner = await screen.findByTestId('acq-nostatement')
    expect(banner).toHaveTextContent('Выписка загружена по 3 сентября. Оплаты после этой даты сверить пока нельзя.')
    expect(screen.getAllByText('нет выписки').length).toBeGreaterThan(0)
  })

  it('has an empty state and an error state', async () => {
    setMockScenario('acqempty')
    const { unmount } = open('/transactions?tab=acquiring')
    expect(await screen.findByText('За сентябрь 2026 оплат картой нет')).toBeInTheDocument()
    unmount()

    setMockScenario('acqerror')
    open('/transactions?tab=acquiring')
    expect(await screen.findByTestId('acq-error')).toHaveTextContent('Не получилось загрузить сверку')
  })
})
