// Parsing money typed by a person. Rule 2 of CLAUDE.md: no floats, the string is split by hand into integer kopecks.

export type AmountError = 'empty' | 'not_number' | 'zero' | 'decimals' | 'too_large'

export type AmountResult = { ok: true; kopecks: number } | { ok: false; error: AmountError }

/** 100 000 000 rubles; anything above is rejected as a typo. */
const MAX_RUBLES = 100_000_000
const SPACES = new RegExp(String.raw`[\s${String.fromCharCode(160)}${String.fromCharCode(0x202f)}]`, 'g')

export function parseAmount(input: string): AmountResult {
  const text = input.replace(SPACES, '')
  if (text === '') return { ok: false, error: 'empty' }
  const match = /^(\d+)(?:[.,](\d*))?$/.exec(text)
  if (!match) return { ok: false, error: 'not_number' }
  const rubles = match[1] ?? '0'
  const fraction = match[2] ?? ''
  if (fraction.length > 2) return { ok: false, error: 'decimals' }
  const rublesValue = Number(rubles)
  const kopecks = Number(fraction.padEnd(2, '0'))
  if (rublesValue === 0 && kopecks === 0) return { ok: false, error: 'zero' }
  if (rublesValue > MAX_RUBLES || (rublesValue === MAX_RUBLES && kopecks > 0)) return { ok: false, error: 'too_large' }
  return { ok: true, kopecks: rublesValue * 100 + kopecks }
}
