import { expect, test, type Locator, type Page, type Response } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Stage 2 e2e: the Dashboard ("Рабочий стол", functions 1-5).
 *
 * Generic part (any clinic with data): every number has a tooltip with breakdown and source; numbers on the screen equal
 * the API response; advice cards open "Почему?"; no horizontal overflow at 1280 / 820 / 390.
 * Golden part (VF_E2E_SET03=1): the clinic is seeded from tests/golden/set03; the page is opened with ?as_of=2026-09-09
 * and compared with set03/expected.json to the kopeck.
 *
 * data-testid and the ?as_of= query parameter are the tester's proposal, see docs/handoff.md
 * (2026-10-12 tester -> frontend-developer, stage 2). Env: VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD.
 */
const url = process.env.VF_WEB_URL;
const email = process.env.VF_E2E_EMAIL;
const password = process.env.VF_E2E_PASSWORD;
const SET03 = process.env.VF_E2E_SET03 === '1';
const AS_OF = '2026-09-09';
const expectedAll = JSON.parse(readFileSync(resolve(__dirname, '../golden/set03/expected.json'), 'utf-8'));
const golden = expectedAll.cases.find((c: { as_of: string }) => c.as_of === AS_OF);

test.skip(!url || !email || !password, 'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD are not set');

/** Every number card of the Dashboard: testid -> where its value lives in the API response. */
const FIGURE_CARDS: Array<{ id: string; path: string[]; kind: 'rub' | 'pct' | 'days' }> = [
  { id: 'balance-total', path: ['balance', 'total'], kind: 'rub' },
  { id: 'balance-bank', path: ['balance', 'bank'], kind: 'rub' },
  { id: 'balance-cash', path: ['balance', 'cash'], kind: 'rub' },
  { id: 'balance-week-change', path: ['balance', 'week_change'], kind: 'rub' },
  { id: 'balance-runway', path: ['balance', 'runway_days'], kind: 'days' },
  { id: 'month-revenue', path: ['month', 'revenue'], kind: 'rub' },
  { id: 'month-expenses', path: ['month', 'expenses'], kind: 'rub' },
  { id: 'month-profit', path: ['month', 'profit'], kind: 'rub' },
  { id: 'month-margin', path: ['month', 'profit_margin_pct'], kind: 'pct' },
];

/** "−1 234 567,89 ₽" (nbsp, thin spaces, U+2212) -> kopecks. Takes the FIRST amount in the text, ignores the sign of "+". */
function toKopecks(text: string): number {
  const clean = text.replace(/[   \s]/g, '').replace(/−/g, '-');
  const m = clean.match(/(-?)(\d+)(?:[,.](\d{1,2}))?/);
  if (!m) throw new Error(`no number in "${text}"`);
  const kop = Number((m[3] ?? '0').padEnd(2, '0'));
  const total = Number(m[2]) * 100 + kop;
  return m[1] === '-' ? -total : total;
}

function firstPercent(text: string): number {
  const m = text.replace(/−/g, '-').replace(/[   ]/g, ' ').match(/(-?\d+(?:[,.]\d+)?)\s?%/);
  if (!m) throw new Error(`no percent in "${text}"`);
  return Number(m[1].replace(',', '.'));
}

function at(obj: any, path: string[]): any {
  return path.reduce((cur, k) => (cur == null ? undefined : cur[k]), obj);
}

async function login(page: Page) {
  await page.goto('/');
  await page.getByLabel(/почт|e-?mail/i).fill(email!);
  await page.getByLabel(/парол/i).fill(password!);
  await page.getByRole('button', { name: /войти|вход/i }).click();
  await expect(page.getByTestId('balance-total')).toBeVisible();
}

/** Opens the Dashboard (optionally with ?as_of=) and returns the JSON of GET /v1/dashboard, or null when no network call is seen (mock mode). */
async function openDashboard(page: Page, asOf?: string): Promise<any | null> {
  const path = new URL(page.url()).pathname;
  const wait = page
    .waitForResponse((r: Response) => r.url().includes('/v1/dashboard') && r.status() === 200, { timeout: 8000 })
    .then((r) => r.json())
    .catch(() => null);
  await page.goto(asOf ? `${path}?as_of=${asOf}` : path);
  await expect(page.getByTestId('balance-total')).toBeVisible();
  return wait;
}

async function openTip(page: Page, card: Locator) {
  const trigger = card.getByTestId('figure-tip-trigger').first();
  await trigger.scrollIntoViewIfNeeded();
  await trigger.hover().catch(() => undefined);
  if (!(await page.getByTestId('figure-tip').isVisible())) await trigger.click();
  await expect(page.getByTestId('figure-tip')).toBeVisible();
  return page.getByTestId('figure-tip');
}

async function closeTip(page: Page) {
  await page.keyboard.press('Escape');
  await page.mouse.move(0, 0);
  if (await page.getByTestId('figure-tip').isVisible()) await page.mouse.click(1, 1);
  await expect(page.getByTestId('figure-tip')).toBeHidden();
}

async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test.describe('Dashboard (stage 2)', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openDashboard(page, SET03 ? AS_OF : undefined);
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test('the header shows the date and when the data was updated', async () => {
    const header = page.getByRole('heading', { name: /рабочий стол/i });
    await expect(header).toBeVisible();
    await expect(page.getByTestId('page-subtitle')).toContainText(/\d{4}/);
  });

  test('every number card is visible and has a tooltip trigger', async () => {
    for (const c of FIGURE_CARDS) {
      const card = page.getByTestId(c.id);
      await expect(card, c.id).toBeVisible();
      await expect(card.getByTestId('figure-tip-trigger').first(), `${c.id}: no tooltip trigger`).toBeVisible();
    }
  });

  test('every tooltip shows at least one breakdown row and a non-empty source', async () => {
    for (const c of FIGURE_CARDS) {
      const tip = await openTip(page, page.getByTestId(c.id));
      expect(await tip.getByTestId('figure-tip-row').count(), `${c.id}: breakdown rows`).toBeGreaterThanOrEqual(1);
      expect((await tip.getByTestId('figure-tip-source').innerText()).trim().length, `${c.id}: source`).toBeGreaterThan(0);
      await closeTip(page);
    }
  });

  test('no money or percent value on the page is left without a tooltip', async () => {
    // Exempt: advice texts (they open "Почему?"), the tooltip itself, elements marked data-no-tip (counters like "9 дней из 30").
    const offenders = await page.evaluate(() => {
      const re = /\d[\d    ]*(?:[,.]\d+)?\s?(₽|%)/;
      const out: string[] = [];
      const root = document.querySelector('main') ?? document.body;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const text = n.textContent ?? '';
        const el = n.parentElement;
        if (!el || !re.test(text)) continue;
        if (el.closest('[data-testid="figure-tip-trigger"], [data-testid="figure-tip"], [data-testid="advice-card"], [data-no-tip]')) continue;
        out.push(text.trim().slice(0, 60));
      }
      return out;
    });
    expect(offenders, `numbers without a tooltip: ${offenders.join(' | ')}`).toEqual([]);
  });

  test('numbers on the screen equal the API response, tooltips equal its breakdown', async () => {
    test.skip(!api, 'no GET /v1/dashboard call observed (mock mode): screen-to-API comparison skipped');
    for (const c of FIGURE_CARDS) {
      const fig = at(api, c.path);
      if (!fig) continue; // week_change is absent for a very young clinic
      const text = await page.getByTestId(c.id).innerText();
      if (c.kind === 'rub') expect(Math.abs(toKopecks(text)), `${c.id} on screen`).toBe(Math.abs(fig.value));
      if (c.kind === 'pct') expect(firstPercent(text), `${c.id} on screen`).toBe(fig.value);
      if (c.kind === 'days') expect(Number(text.replace(/ | /g, ' ').match(/\d+/)?.[0]), `${c.id} on screen`).toBe(fig.value);
      if (c.kind === 'rub') {
        const tip = await openTip(page, page.getByTestId(c.id));
        const rows = await tip.getByTestId('figure-tip-row').allInnerTexts();
        const shown = rows.map((r) => Math.abs(toKopecks(r.split('\n').pop() ?? r))).sort((a, b) => a - b);
        const wanted = fig.breakdown.map((b: { value: number }) => Math.abs(b.value)).sort((a: number, b: number) => a - b);
        expect(shown, `${c.id}: tooltip rows`).toEqual(wanted);
        await closeTip(page);
      }
    }
  });

  test('advice cards: "Почему?" opens a breakdown with steps and sources and closes again', async () => {
    const cards = page.getByTestId('advice-card');
    const n = await cards.count();
    test.skip(n === 0, 'no advice for this clinic and date');
    for (let i = 0; i < n; i++) {
      const card = cards.nth(i);
      const button = card.getByTestId('advice-why');
      await expect(button).toContainText(/почему/i);
      await button.click();
      const body = card.getByTestId('advice-why-body');
      await expect(body).toBeVisible();
      expect(await body.getByTestId('advice-why-step').count(), 'steps').toBeGreaterThanOrEqual(2);
      expect((await body.getByTestId('advice-why-sources').innerText()).trim().length).toBeGreaterThan(0);
      await expect(button).toContainText(/свернуть/i);
      await button.click();
      await expect(body).toBeHidden();
    }
  });

  test('advice cards are sorted alert, warning, good and carry their id', async () => {
    const sev = await page.getByTestId('advice-card').evaluateAll((els) => els.map((e) => e.getAttribute('data-severity')));
    const rank: Record<string, number> = { alert: 0, warning: 1, good: 2 };
    expect(sev.every((s) => s !== null && s in rank)).toBe(true);
    expect(sev.map((s) => rank[s as string])).toEqual([...sev.map((s) => rank[s as string])].sort());
    const ids = await page.getByTestId('advice-card').evaluateAll((els) => els.map((e) => e.getAttribute('data-advice-id')));
    expect(new Set(ids).size).toBe(ids.length);
    if (api) expect(ids).toEqual(api.advice.map((a: { id: string }) => a.id));
  });

  test('the balance chart is drawn and has an accessible description', async () => {
    const chart = page.getByTestId('balance-trend');
    await expect(chart).toBeVisible();
    const box = await chart.boundingBox();
    expect(box && box.width > 100 && box.height > 40).toBe(true);
    expect(((await chart.getAttribute('aria-label')) ?? (await chart.innerText())).trim().length).toBeGreaterThan(0);
  });

  test('no roles, no "Ответ ИИ", no branches (specification: no roles in MVP)', async () => {
    const text = (await page.locator('main').innerText()).toLowerCase();
    for (const bad of ['только просмотр', 'ответ ии', 'филиал']) expect(text).not.toContain(bad);
  });

  test('layout: no horizontal overflow; cards stack on a phone and sit in a row on a desktop', async ({}, info) => {
    await noHorizontalOverflow(page);
    const width = info.project.use.viewport?.width ?? 1280;
    const boxes = await Promise.all(['month-revenue', 'month-expenses', 'month-profit'].map((id) => page.getByTestId(id).boundingBox()));
    expect(boxes.every(Boolean)).toBe(true);
    const [a, b, c] = boxes as Array<{ x: number; y: number }>;
    if (width >= 1280) expect(Math.abs(a.y - b.y) < 4 && Math.abs(b.y - c.y) < 4, 'month cards in one row').toBe(true);
    if (width <= 390) expect(Math.abs(a.x - b.x) < 4 && b.y > a.y && c.y > b.y, 'month cards stacked').toBe(true);
  });
});

test.describe('Dashboard on golden set03 (VF_E2E_SET03=1, ?as_of=2026-09-09)', () => {
  test.skip(!SET03, 'VF_E2E_SET03=1 and a clinic seeded from tests/golden/set03 are required');
  let page: Page;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    await openDashboard(page, AS_OF);
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test('money cards show the golden numbers to the kopeck', async () => {
    const expectKop = async (id: string, kop: number) =>
      expect(Math.abs(toKopecks(await page.getByTestId(id).innerText())), id).toBe(Math.abs(kop));
    await expectKop('balance-total', golden.balance.total.value);
    await expectKop('balance-bank', golden.balance.bank.value);
    await expectKop('balance-cash', golden.balance.cash.value);
    await expectKop('balance-week-change', golden.week_change.value);
    await expectKop('month-revenue', golden.month.revenue.value);
    await expectKop('month-expenses', golden.month.expenses.value);
    await expectKop('month-profit', golden.month.profit.value);
    expect(firstPercent(await page.getByTestId('month-margin').innerText())).toBe(golden.month.profit_margin_pct.value);
    const runway = (await page.getByTestId('balance-runway').innerText()).match(/\d+/)?.[0];
    expect(Number(runway)).toBe(golden.runway_days.value);
  });

  test('the total balance tooltip lists the three accounts of the golden clinic', async () => {
    const tip = await openTip(page, page.getByTestId('balance-total'));
    const text = await tip.innerText();
    for (const name of Object.keys(golden.balance.total.breakdown)) expect(text).toContain(name);
    await closeTip(page);
  });

  test('the expenses tooltip is the category breakdown; the check debit is "Без статьи", the salary advance of 10 Sept is absent', async () => {
    const tip = await openTip(page, page.getByTestId('month-expenses'));
    const text = await tip.innerText();
    for (const name of Object.keys(golden.month.expenses.breakdown)) expect(text).toContain(name);
    expect(text).not.toContain('Зарплата');
    await closeTip(page);
  });

  test('advice: the golden ids in order, each "Почему?" holds the numbers of the calculation', async () => {
    const cards = page.getByTestId('advice-card');
    await expect(cards).toHaveCount(golden.advice.length);
    const ids = await cards.evaluateAll((els) => els.map((e) => e.getAttribute('data-advice-id')));
    expect(ids).toEqual(golden.advice.map((a: { id: string }) => a.id));
    for (let i = 0; i < golden.advice.length; i++) {
      const exp = golden.advice[i];
      await cards.nth(i).getByTestId('advice-why').click();
      const body = (await cards.nth(i).getByTestId('advice-why-body').innerText()).replace(/[   ]/g, ' ');
      for (const kop of exp.why_amounts as number[]) {
        const rub = Math.floor(Math.abs(kop) / 100);
        const rest = Math.abs(kop) % 100;
        const text = rub.toLocaleString('ru-RU').replace(/[  ]/g, ' ') + (rest ? `,${String(rest).padStart(2, '0')}` : '');
        expect(body, `${exp.id}: ${text}`).toContain(text);
      }
      for (const p of exp.why_pcts as string[]) expect(body, `${exp.id}: ${p}`).toContain(p);
      await cards.nth(i).getByTestId('advice-why').click();
    }
  });

  test('no horizontal overflow with the golden data', async () => {
    await noHorizontalOverflow(page);
  });
});
