import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '../..')

// Copies of design files must match the source in design/. Fix with: npm run sync:design
describe.skipIf(!existsSync(resolve(root, '../design/tokens.css')))('design copies', () => {
  it.each([
    ['../design/tokens.css', 'src/styles/tokens.css'],
    ['../design/icons.svg', 'src/assets/icons.svg'],
  ])('%s is in sync with %s', (source, copy) => {
    expect(readFileSync(resolve(root, copy), 'utf8')).toBe(readFileSync(resolve(root, source), 'utf8'))
  })
})
