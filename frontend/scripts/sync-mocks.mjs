// Copies the report examples of the contract (made by backend/scripts/export_openapi.py from the golden set)
// next to the mock server, so that the frontend builds and works without the rest of the repository.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const from = resolve(root, '../backend/openapi.json')
const to = resolve(root, 'src/mocks/data/reports_set04.json')
const schemas = JSON.parse(readFileSync(from, 'utf8')).components.schemas
function example(name) {
  const value = schemas[name]?.example
  if (!value) throw new Error(`Missing ${name}.example in ${from}; run backend/scripts/export_openapi.py`)
  return structuredClone(value)
}
const direction = example('PnlOut')
if (direction.view !== 'direction' || !direction.directions || !direction.common_variable) {
  throw new Error('PnlOut.example must include the direction view')
}
const clinic = structuredClone(direction)
clinic.view = 'clinic'
delete clinic.directions
delete clinic.common_variable
const reports = {
  pnl_clinic: clinic,
  pnl_direction: direction,
  norm: example('NormOut'),
  stock: example('StockOut'),
  stock_idle: example('StockIdleOut'),
}
mkdirSync(dirname(to), { recursive: true })
writeFileSync(to, JSON.stringify(reports, null, 2) + '\n')
process.stdout.write('../backend/openapi.json -> src/mocks/data/reports_set04.json\n')
