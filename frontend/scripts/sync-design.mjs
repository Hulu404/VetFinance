// Copies design tokens and icon sprite from ../design into src. Source of truth stays in design/.
import { copyFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pairs = [
  ['../design/tokens.css', 'src/styles/tokens.css'],
  ['../design/icons.svg', 'src/assets/icons.svg'],
]
for (const [from, to] of pairs) {
  const src = resolve(root, from)
  if (!existsSync(src)) {
    process.stderr.write(`design file not found: ${src}\n`)
    process.exit(1)
  }
  copyFileSync(src, resolve(root, to))
  process.stdout.write(`${from} -> ${to}\n`)
}
