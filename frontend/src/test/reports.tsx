import { useLocation } from 'react-router-dom'
import { vi } from 'vitest'

/** Shows the address, so a test can read what the screen wrote into it. */
export function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>
}

/** Makes `matchMedia` answer `(max-width: Npx)` queries for a window of the given width. */
export function stubWidth(width: number): void {
  vi.stubGlobal('matchMedia', (query: string) => {
    const limit = /max-width:\s*(\d+)px/.exec(query)
    return {
      matches: limit ? width <= Number(limit[1]) : false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
      onchange: null,
    }
  })
}

const MONEY_OR_PERCENT = new RegExp(String.raw`\d[\d\s]*(?:[,.]\d+)?\s?(₽|%)`)
const EXEMPT =
  '[data-figure], [data-testid="figure-tip-trigger"], [data-testid="figure-tip"], [data-no-tip], [data-testid$="-headline"], ' +
  '[data-testid$="-footnote"], [data-testid$="-month"], [data-testid="page-subtitle"], [data-testid$="-period-status"], [data-testid$="-banner"]'

/**
 * The rule of design/screens/pnl.md, "data-testid для e2e": a sum or a percent outside an element with `data-figure`
 * (or a listed exception) is a number without a tip. Same logic as `numbersWithoutTooltip` of tests/e2e/reports.spec.ts.
 */
export function numbersWithoutTip(root: HTMLElement): string[] {
  const found: string[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? ''
    const element = node.parentElement
    if (!element || !MONEY_OR_PERCENT.test(text)) continue
    if (element.closest(EXEMPT)) continue
    found.push(text.trim().slice(0, 60))
  }
  return found
}
