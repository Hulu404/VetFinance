import { describe, expect, it } from 'vitest'
import { asOfFromSearch } from './asOf'

describe('asOfFromSearch', () => {
  it('reads a valid date from the query string', () => {
    expect(asOfFromSearch('?as_of=2026-09-09')).toBe('2026-09-09')
    expect(asOfFromSearch('?tab=check&as_of=2026-09-09')).toBe('2026-09-09')
  })

  it('ignores a missing or malformed value', () => {
    expect(asOfFromSearch('')).toBeNull()
    expect(asOfFromSearch('?as_of=')).toBeNull()
    expect(asOfFromSearch('?as_of=9-sep')).toBeNull()
    expect(asOfFromSearch('?as_of=2026-13-01')).toBeNull()
  })
})
