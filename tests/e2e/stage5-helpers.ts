import { expect, type Locator, type Page, type Response } from '@playwright/test';

/** Shared helpers of price.spec.ts and efficiency.spec.ts (not a spec: the file name has no `.spec`). */
export const url = process.env.VF_WEB_URL;
export const email = process.env.VF_E2E_EMAIL;
export const password = process.env.VF_E2E_PASSWORD;
export const SET06 = process.env.VF_E2E_SET06 === '1';
export const WRITE = process.env.VF_E2E_WRITE === '1';

/** "−1 234 567,89 ₽" (nbsp, thin spaces, U+2212) -> kopecks, signed. */
export function toKopecks(text: string): number {
  const clean = text.replace(/[\s  ]/g, '').replace(/−/g, '-');
  const m = clean.match(/(-?)(\d+)(?:[,.](\d{1,2}))?/);
  if (!m) throw new Error(`no number in "${text}"`);
  const v = Number(m[2]) * 100 + Number((m[3] ?? '0').padEnd(2, '0'));
  return m[1] ? -v : v;
}

/** "26,0%" / "−6,3%" -> 26 / -6.3 */
export function toPct(text: string): number {
  const m = text.replace(/[\s  ]/g, '').replace(/−/g, '-').match(/(-?\d+(?:[,.]\d+)?)%/);
  if (!m) throw new Error(`no percent in "${text}"`);
  return Number(m[1].replace(',', '.'));
}

/** The amount as it may be printed: "108 500 ₽", "76 663,82 ₽" (any spaces). */
export function rubText(kopecks: number): RegExp {
  const r = Math.floor(Math.abs(kopecks) / 100);
  const k = Math.abs(kopecks) % 100;
  const body = String(r).replace(/\B(?=(\d{3})+(?!\d))/g, '[\\s\\u00a0\\u202f]?') + (k ? `,${String(k).padStart(2, '0')}` : '(,00)?');
  return new RegExp(body);
}

/** Russian plural for a count: ruPlural(544, 'час', 'часа', 'часов') -> 'часа' (1 час, 2-4 часа, 5-20 и 11-14 часов). */
export function ruPlural(n: number, one: string, few: string, many: string): string {
  const m100 = Math.abs(n) % 100;
  const m10 = m100 % 10;
  if (m100 >= 11 && m100 <= 14) return many;
  if (m10 === 1) return one;
  if (m10 >= 2 && m10 <= 4) return few;
  return many;
}

export const norm = (s: string): string => s.replace(/[\s  ]+/g, ' ').trim();
export const val = (fig: any): number | null => (fig && typeof fig === 'object' ? fig.value : (fig ?? null));
export const q = (...parts: string[]) => parts.filter(Boolean).join('&');

export async function login(page: Page) {
  await page.goto('/');
  await page.getByLabel(/почт|e-?mail/i).fill(email!);
  await page.getByLabel(/парол/i).fill(password!);
  await page.getByRole('button', { name: /войти|вход/i }).click();
  await expect(page.getByTestId('balance-total')).toBeVisible();
}

/** Opens a page and returns the JSON of the first matching GET response (null in mock mode). */
export async function openPage(page: Page, path: string, apiPart: string, query: string): Promise<any | null> {
  const wait = page
    .waitForResponse((r: Response) => r.url().includes(apiPart) && r.request().method() === 'GET' && r.status() === 200, { timeout: 8000 })
    .then((r) => r.json())
    .catch(() => null);
  await page.goto(`${path}${query ? `?${query}` : ''}`);
  return wait;
}

export async function openTip(page: Page, trigger: Locator) {
  const button = trigger.getByTestId('figure-tip-trigger');
  if (await button.count()) trigger = button.first();
  await trigger.scrollIntoViewIfNeeded();
  await trigger.hover().catch(() => undefined);
  if (!(await page.getByTestId('figure-tip').isVisible())) await trigger.click();
  await expect(page.getByTestId('figure-tip')).toBeVisible();
  return page.getByTestId('figure-tip');
}

export async function closeTip(page: Page) {
  await page.keyboard.press('Escape');
  await page.mouse.move(0, 0);
  if (await page.getByTestId('figure-tip').isVisible()) await page.mouse.click(1, 1);
  await expect(page.getByTestId('figure-tip')).toBeHidden();
}

export async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

/** Words that must not appear on the stage 5 screens (price.md, efficiency.md: «Тексты экрана»). */
export async function forbiddenWords(page: Page): Promise<string[]> {
  const text = (await page.locator('main').innerText()).toLowerCase();
  return [/\bии\b/, /нейросет/, /только просмотр/, /филиал/, /\bроль\b/, /\bбот\b/, /катастроф/, /банкротств/, /резерв роста/, /простой/]
    .filter((re) => re.test(text))
    .map(String);
}

/** Field of a form: the testid marks the input or its wrapper. */
export async function fieldOf(page: Page, testId: string): Promise<Locator> {
  const el = page.getByTestId(testId);
  const input = el.locator('input, select, textarea');
  return (await input.count()) ? input.first() : el;
}

/** Opens a page with the answer of the API changed by `patch` (for states that the data of the clinic cannot produce). */
export async function withAnswer(page: Page, apiGlob: string, path: string, patch: (body: any) => void) {
  await page.route(apiGlob, async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    patch(body);
    await route.fulfill({ response: res, json: body });
  });
  await page.goto(path);
}
