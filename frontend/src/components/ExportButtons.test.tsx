import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setMockScenario } from '../mocks/scenario'
import { server } from '../mocks/server'
import { saveBlob } from '../lib/saveBlob'
import { renderWithQuery } from '../test/render'
import { ExportButtons } from './ExportButtons'

vi.mock('../lib/saveBlob', () => ({ saveBlob: vi.fn() }))

function setup(props: Partial<ComponentProps<typeof ExportButtons>> = {}) {
  return renderWithQuery(<ExportButtons report="pnl" month="2026-09" asOf={null} disabled={false} {...props} />, { toasts: true })
}

beforeEach(() => {
  vi.mocked(saveBlob).mockClear()
})

describe('ExportButtons', () => {
  it('fetches the file with the token for the month on the screen, saves it and says its name', async () => {
    const user = userEvent.setup()
    const asked: Request[] = []
    server.events.on('request:start', ({ request }) => asked.push(request))
    setup({ asOf: '2026-09-30' })

    await user.click(screen.getByTestId('pnl-export-xlsx'))

    await waitFor(() => expect(saveBlob).toHaveBeenCalledTimes(1))
    const call = vi.mocked(saveBlob).mock.calls[0]
    expect(call?.[1]).toBe('vetfinance-pnl-2026-09.xlsx')
    expect(call?.[0]).toBeInstanceOf(Blob)
    expect(await screen.findByText('Файл готов: vetfinance-pnl-2026-09.xlsx')).toBeInTheDocument()
    const exportRequest = asked.find((request) => request.url.includes('/export'))
    expect(exportRequest?.url).toContain('/v1/reports/pnl/export?format=xlsx&month=2026-09&as_of=2026-09-30')
    expect(exportRequest?.headers.get('Authorization')).toBe('Bearer test-token')
    server.events.removeAllListeners()
  })

  it('writes "Готовим файл…" on the pressed button and holds both while the file is made', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByTestId('pnl-export-pdf'))

    expect(screen.getByTestId('pnl-export-pdf')).toHaveTextContent('Готовим файл…')
    expect(screen.getByTestId('pnl-export-pdf')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
    await waitFor(() => expect(saveBlob).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('pnl-export-pdf')).toHaveTextContent('Скачать PDF'))
    expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'false')
  })

  it('does nothing when the report is loading or empty', async () => {
    const user = userEvent.setup()
    const asked: string[] = []
    server.events.on('request:start', ({ request }) => asked.push(request.url))
    setup({ disabled: true })

    await user.click(screen.getByTestId('pnl-export-xlsx'))

    expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'true')
    expect(asked.some((url) => url.includes('/export'))).toBe(false)
    expect(saveBlob).not.toHaveBeenCalled()
    server.events.removeAllListeners()
  })

  it('shows the usual error toast when the backend answers 501, and frees the buttons', async () => {
    const user = userEvent.setup()
    setMockScenario('exportfail')
    setup()

    await user.click(screen.getByTestId('pnl-export-xlsx'))

    expect(await screen.findByText('Не получилось подготовить файл. Попробуйте ещё раз.')).toBeInTheDocument()
    expect(saveBlob).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'false'))
  })

  it('tells to wait a minute on 429', async () => {
    const user = userEvent.setup()
    server.use(http.get('*/v1/reports/pnl/export', () => HttpResponse.json({ error: { code: 'rate_limited', message: 'x', details: {} } }, { status: 429 })))
    setup()

    await user.click(screen.getByTestId('pnl-export-xlsx'))

    expect(await screen.findByText('Слишком много запросов. Подождите минуту.')).toBeInTheDocument()
  })

  it('takes the name of the file from the headers; stock has no month in the request', async () => {
    const user = userEvent.setup()
    const asked: string[] = []
    server.events.on('request:start', ({ request }) => asked.push(request.url))
    setup({ report: 'stock', month: null })

    await user.click(screen.getByTestId('stock-export-pdf'))

    await waitFor(() => expect(saveBlob).toHaveBeenCalled())
    expect(asked.find((url) => url.includes('/export'))).toContain('/v1/reports/stock/export?format=pdf')
    expect(asked.find((url) => url.includes('/export'))).not.toContain('month=')
    server.events.removeAllListeners()
  })
})
