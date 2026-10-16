import { describe, expect, it } from 'vitest'
import { filenameFromDisposition } from './client'

describe('filenameFromDisposition', () => {
  it('reads a quoted file name', () => {
    expect(filenameFromDisposition('attachment; filename="vetfinance-pnl-2026-09.xlsx"')).toBe('vetfinance-pnl-2026-09.xlsx')
  })

  it('reads an unquoted one', () => {
    expect(filenameFromDisposition('attachment; filename=vetfinance-norm-2026-08.pdf')).toBe('vetfinance-norm-2026-08.pdf')
  })

  it('prefers the encoded form', () => {
    expect(filenameFromDisposition("attachment; filename=\"x.pdf\"; filename*=UTF-8''%D0%BE%D1%82%D1%87%D1%91%D1%82.pdf")).toBe('отчёт.pdf')
  })

  it('returns null when there is no header or no name', () => {
    expect(filenameFromDisposition(null)).toBeNull()
    expect(filenameFromDisposition('attachment')).toBeNull()
  })
})
