import { expect, test, type Locator, type Page, type Response } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

/**
 * Stage 3 e2e: the reports "Прибыль и убытки", "Норма", "Склад и сроки" (functions 14, 15, 17, 18, 20).
 *
 * data-testid come from design/screens/pnl.md, norm.md, stock.md and dashboard.md (after the designer's edits of 2026-10-14);
 * extra ones the tester asked for are listed in docs/handoff.md ("tester -> frontend-developer (этап 3)").
 * Routes: /reports/pnl, /reports/norm, /reports/stock; query: ?month=YYYY-MM&view=clinic|direction and, for every report,
 * ?as_of=YYYY-MM-DD (passed to the API as is: a running month, the golden date).
 * Owner decisions of 2026-10-14 that are checked here: the profit on the Dashboard is "Прибыль по деньгам" with a link to the report;
 * the write-off row of "Норма" is a memo row outside the sum of shares; a running month is not rated (banner, no statuses);
 * "Склад": expired batches are a separate figure (stock-expired) and not in the expiring list.
 *
 * Generic part (any clinic with data): rows and tooltips, screen numbers equal the API response, the identity of the P&L on the
 * screen, view and month switching, export buttons, states, no forbidden words, no horizontal overflow at 1280 / 820 / 390.
 * Golden part (VF_E2E_SET04=1, clinic seeded from tests/golden/set04): numbers equal expected.json to the kopeck.
 * Downloaded exports are saved to VF_E2E_DOWNLOADS (<report>-<month>.xlsx|pdf); pytest tests/contract/test_stage3_contract.py
 * (VF_E2E_DOWNLOADS=...) then compares those very files with the API.
 * Env: VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD.
 */
const url = process.env.VF_WEB_URL;
const email = process.env.VF_E2E_EMAIL;
const password = process.env.VF_E2E_PASSWORD;
const SET04 = process.env.VF_E2E_SET04 === '1';
const DOWNLOADS = process.env.VF_E2E_DOWNLOADS;
const MONTH = '2026-09';
const STOCK_AS_OF = '2026-09-30';
const expectedAll = JSON.parse(readFileSync(resolve(__dirname, '../golden/set04/expected.json'), 'utf-8'));
const PNL_ROW_ORDER = ['revenue', 'variable', 'marginal_profit', 'fixed', 'fixed_payroll', 'fixed_other', 'taxes', 'obligations', 'net_profit'];

test.skip(!url || !email || !password, 'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD are not set');

// ---------------------------------------------------------------- helpers
/** "−1 234 567,89 ₽" (nbsp, thin spaces, U+2212) -> kopecks (absolute value; the sign is checked separately). */
function toKopecks(text: string): number {
  const clean = text.replace(/[   \s]/g, '').replace(/−/g, '-');
  const m = clean.match(/(\d+)(?:[,.](\d{1,2}))?/);
  if (!m) throw new Error(`no number in "${text}"`);
  return Number(m[1]) * 100 + Number((m[2] ?? '0').padEnd(2, '0'));
}

/** First percent in the text, "12,3%" -> 12.3. */
function firstPercent(text: string): number {
  const m = text.replace(/−/g, '-').replace(/[   ]/g, ' ').match(/(-?\d+(?:[,.]\d+)?)\s?%/);
  if (!m) throw new Error(`no percent in "${text}"`);
  return Number(m[1].replace(',', '.'));
}

const hasMinus = (text: string) => /^[\s]*[−-]/.test(text);

async function login(page: Page) {
  await page.goto('/');
  await page.getByLabel(/почт|e-?mail/i).fill(email!);
  await page.getByLabel(/парол/i).fill(password!);
  await page.getByRole('button', { name: /войти|вход/i }).click();
  await expect(page.getByTestId('balance-total')).toBeVisible();
}

/** Opens a report page and returns the JSON of the report request (null in mock mode: no network call seen). */
async function openReport(page: Page, path: string, apiPart: string, query: string): Promise<any | null> {
  const wait = page
    .waitForResponse((r: Response) => r.url().includes(apiPart) && !r.url().includes('/export') && r.status() === 200, { timeout: 8000 })
    .then((r) => r.json())
    .catch(() => null);
  await page.goto(`${path}${query ? `?${query}` : ''}`);
  return wait;
}

async function openTip(page: Page, trigger: Locator) {
  // Some testids mark a cell around the button, others the trigger itself.
  // Locator.or() is a union, not a fallback: a cell and its child match twice.
  const button = trigger.getByTestId('figure-tip-trigger');
  if (await button.count()) trigger = button.first();
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

/** Money or percent on the page that does not sit inside an element with data-figure / a tooltip trigger / an exempt block. */
async function numbersWithoutTooltip(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const re = /\d[\d    ]*(?:[,.]\d+)?\s?(₽|%)/;
    const out: string[] = [];
    const root = document.querySelector('main') ?? document.body;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const exempt =
      '[data-figure], [data-testid="figure-tip-trigger"], [data-testid="figure-tip"], [data-no-tip], [data-testid$="-headline"], ' +
      '[data-testid$="-footnote"], [data-testid$="-month"], [data-testid="page-subtitle"], [data-testid$="-period-status"], [data-testid$="-banner"]';
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = n.textContent ?? '';
      const el = n.parentElement;
      if (!el || !re.test(text)) continue;
      if (el.closest(exempt)) continue;
      out.push(text.trim().slice(0, 60));
    }
    return out;
  });
}

async function forbiddenWords(page: Page): Promise<string[]> {
  const text = (await page.locator('main').innerText()).toLowerCase();
  return [/\bии\b/, /ответ ии/, /только просмотр/, /филиал/, /\bбот\b/, /\bроль\b/, /опасно/, /катастроф/]
    .filter((re) => re.test(text))
    .map(String);
}

async function downloadAndCheck(page: Page, button: Locator, report: string, month: string | null, ext: 'xlsx' | 'pdf') {
  const exportResponse = page.waitForResponse((r) => r.url().includes(`/v1/reports/${report}/export`) && r.status() === 200, { timeout: 15000 }).catch(() => null);
  const [download] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), button.click()]);
  const name = download.suggestedFilename();
  expect(name, 'file name').toMatch(new RegExp(`\\.${ext}$`));
  const res = await exportResponse;
  if (res) {
    const u = new URL(res.url());
    expect(u.searchParams.get('format')).toBe(ext);
    if (month) expect(u.searchParams.get('month'), 'the file is requested for the month on the screen').toBe(month);
    expect(res.headers()['content-type'] ?? '').toContain(ext === 'xlsx' ? 'spreadsheetml' : 'pdf');
  }
  if (DOWNLOADS) {
    mkdirSync(DOWNLOADS, { recursive: true });
    await download.saveAs(join(DOWNLOADS, `${report}-${month ?? 'current'}.${ext}`));
  }
}

function at(obj: any, path: string[]): any {
  return path.reduce((cur, k) => (cur == null ? undefined : cur[k]), obj);
}

// ================================================================== P&L
test.describe('P&L (stage 3, function 14, 18, 20)', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openReport(page, '/reports/pnl', '/v1/reports/pnl', `month=${MONTH}&view=clinic`);
    await expect(page.getByTestId('pnl')).toBeVisible();
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  const rowKeys = async () => page.getByTestId('pnl-row').evaluateAll((els) => els.map((e) => e.getAttribute('data-key')));

  test('the nine rows come in order and the obligations row is there', async () => {
    const keys = (await rowKeys()).filter((k): k is string => !!k);
    expect(keys).toEqual(PNL_ROW_ORDER);
    await expect(page.getByTestId('pnl-row').filter({ has: page.locator('[data-key="obligations"]') }).or(page.locator('[data-testid="pnl-row"][data-key="obligations"]'))).toContainText('Обязательства и амортизация');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Прибыль и убытки');
  });

  test('every amount and share on the screen equals the API response', async () => {
    test.skip(!api, 'no GET /v1/reports/pnl call observed (mock mode)');
    const flat: Record<string, any> = {};
    for (const r of api.rows) {
      flat[r.key] = r;
      for (const c of r.children ?? []) flat[c.key] = c;
    }
    for (const key of PNL_ROW_ORDER) {
      const amount = page.locator(`[data-testid="pnl-row-amount"][data-key="${key}"]`);
      expect(Math.abs(toKopecks(await amount.innerText())), `${key}: amount`).toBe(Math.abs(flat[key].amount.value));
      const share = page.locator(`[data-testid="pnl-row-share"][data-key="${key}"]`);
      if (flat[key].share_pct) expect(firstPercent(await share.innerText()), `${key}: share`).toBe(flat[key].share_pct.value);
    }
  });

  test('expense rows are shown with the minus sign, profit and subtotal without it unless negative', async () => {
    for (const key of ['variable', 'fixed', 'taxes', 'obligations']) {
      const text = await page.locator(`[data-testid="pnl-row-amount"][data-key="${key}"]`).innerText();
      if (toKopecks(text) !== 0) expect(hasMinus(text), `${key} must start with a minus: "${text}"`).toBe(true);
    }
  });

  test('the identity holds on the screen: revenue - variable - fixed - taxes - obligations = net profit', async () => {
    const k = async (key: string) => toKopecks(await page.locator(`[data-testid="pnl-row-amount"][data-key="${key}"]`).innerText());
    const net = await page.locator('[data-testid="pnl-row-amount"][data-key="net_profit"]').innerText();
    const netValue = hasMinus(net) ? -(await k('net_profit')) : await k('net_profit');
    expect((await k('revenue')) - (await k('variable')) - (await k('fixed')) - (await k('taxes')) - (await k('obligations'))).toBe(netValue);
    expect((await k('fixed_payroll')) + (await k('fixed_other'))).toBe(await k('fixed'));
    expect((await k('revenue')) - (await k('variable'))).toBe(await k('marginal_profit'));
  });

  test('every amount and share opens a tooltip with a breakdown row and a source', async () => {
    for (const key of PNL_ROW_ORDER) {
      for (const id of ['pnl-row-amount', 'pnl-row-share']) {
        const el = page.locator(`[data-testid="${id}"][data-key="${key}"]`);
        if ((await el.count()) === 0) continue;
        const tip = await openTip(page, el);
        expect(await tip.getByTestId('figure-tip-row').count(), `${key}/${id}: breakdown rows`).toBeGreaterThanOrEqual(1);
        expect((await tip.getByTestId('figure-tip-source').innerText()).trim().length, `${key}/${id}: source`).toBeGreaterThan(0);
        expect((await tip.getByTestId('figure-tip-note').innerText()).trim().length, `${key}/${id}: note`).toBeGreaterThan(0);
        await closeTip(page);
      }
    }
  });

  test('the tooltip of net profit lists the five lines of the identity', async () => {
    test.skip(!api, 'mock mode');
    const el = page.locator('[data-testid="pnl-row-amount"][data-key="net_profit"]');
    const tip = await openTip(page, el);
    const net = api.rows.find((r: any) => r.key === 'net_profit');
    const shown = (await tip.getByTestId('figure-tip-row').allInnerTexts()).map((t) => Math.abs(toKopecks(t.split('\n').pop() ?? t))).sort((a, b) => a - b);
    expect(shown).toEqual(net.amount.breakdown.map((b: any) => Math.abs(b.value)).sort((a: number, b: number) => a - b));
    await closeTip(page);
  });

  test('no money or percent value is left without a tooltip', async () => {
    const offenders = await numbersWithoutTooltip(page);
    expect(offenders, `numbers without a tooltip: ${offenders.join(' | ')}`).toEqual([]);
  });

  test('no forbidden words on the screen', async () => {
    expect(await forbiddenWords(page)).toEqual([]);
  });

  test('the view switch asks for view=direction and the bridge to the marginal profit holds', async ({}, info) => {
    const wait = page.waitForResponse((r) => r.url().includes('/v1/reports/pnl') && r.url().includes('view=direction') && r.status() === 200, { timeout: 8000 }).then((r) => r.json()).catch(() => null);
    await page.getByTestId('pnl-view-direction').click();
    await expect(page.getByTestId('pnl-view-direction')).toHaveAttribute('aria-checked', 'true');
    const dir = await wait;
    const row = (key: string) => page.locator(`[data-testid="pnl-direction"][data-key="${key}"]`);
    for (const key of ['services', 'goods', 'common', 'total']) await expect(row(key), key).toBeVisible();
    const margin = async (key: string) => toKopecks(await row(key).getByTestId('pnl-direction-margin').innerText());
    const revenue = async (key: string) => toKopecks(await row(key).getByTestId('pnl-direction-revenue').innerText());
    const marginalProfit = await margin('total');
    const commonText = await row('common').getByTestId('pnl-direction-margin').innerText();
    const common = toKopecks(commonText);
    expect((await margin('services')) + (await margin('goods')) - common, 'margin(services) + margin(goods) - common = marginal profit').toBe(marginalProfit);
    expect((await revenue('services')) + (await revenue('goods'))).toBe(await revenue('total'));
    if (dir) {
      for (const d of dir.directions) {
        expect(Math.abs(toKopecks(await row(d.direction).getByTestId('pnl-direction-revenue').innerText()))).toBe(Math.abs(d.revenue.value));
        expect(Math.abs(toKopecks(await row(d.direction).getByTestId('pnl-direction-margin').innerText()))).toBe(Math.abs(d.margin.value));
      }
    }
    const offenders = await numbersWithoutTooltip(page);
    expect(offenders, `numbers without a tooltip in the direction view: ${offenders.join(' | ')}`).toEqual([]);
    if ((info.project.use.viewport?.width ?? 1280) <= 390) await noHorizontalOverflow(page);
    await page.getByTestId('pnl-view-clinic').click();
    await expect(page.getByTestId('pnl-row').first()).toBeVisible();
  });

  test('switching to the previous month asks the API for that month and the numbers follow', async () => {
    const wait = page.waitForResponse((r) => r.url().includes('/v1/reports/pnl') && r.url().includes('month=2026-08') && r.status() === 200, { timeout: 8000 }).then((r) => r.json()).catch(() => null);
    await page.getByTestId('pnl-month-prev').click();
    const prev = await wait;
    await expect(page).toHaveURL(/month=2026-08/);
    if (prev) {
      const revenue = prev.rows.find((r: any) => r.key === 'revenue').amount.value;
      await expect(page.locator('[data-testid="pnl-row-amount"][data-key="revenue"]')).toContainText(new RegExp(String(Math.floor(revenue / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, '\\s?')));
    }
    await page.getByTestId('pnl-month-next').click();
    await expect(page).toHaveURL(/month=2026-09/);
  });

  test('export: Excel and PDF are downloaded for the month on the screen', async () => {
    await downloadAndCheck(page, page.getByTestId('pnl-export-xlsx'), 'pnl', MONTH, 'xlsx');
    await downloadAndCheck(page, page.getByTestId('pnl-export-pdf'), 'pnl', MONTH, 'pdf');
  });

  test('layout: no horizontal overflow; on a phone the share moves under the name', async ({}, info) => {
    await noHorizontalOverflow(page);
    const width = info.project.use.viewport?.width ?? 1280;
    const name = await page.locator('[data-testid="pnl-row"][data-key="variable"]').boundingBox();
    const share = await page.locator('[data-testid="pnl-row-share"][data-key="variable"]').boundingBox();
    expect(name && share).toBeTruthy();
    if (width <= 390) expect(share!.y, 'share below the row name on 390').toBeGreaterThan(name!.y + 4);
    else expect(Math.abs(share!.y - name!.y), 'share in the same line on 820 and 1280').toBeLessThan(name!.height);
  });
});

test.describe('P&L states', () => {
  test('a month without data shows the empty card and disables the export', async ({ page }) => {
    await login(page);
    await page.goto('/reports/pnl?month=2000-01');
    await expect(page.getByTestId('pnl-empty')).toBeVisible();
    await expect(page.getByTestId('pnl-export-xlsx')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.getByTestId('pnl-month-prev')).toBeVisible();
  });

  test('a server error shows the error card with Retry, and Retry loads the report', async ({ page }) => {
    await login(page);
    await page.route('**/v1/reports/pnl**', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":{"code":"sync_failed","message":"x","details":{}}}' }));
    await page.goto(`/reports/pnl?month=${MONTH}`);
    await expect(page.getByTestId('pnl-error')).toBeVisible();
    await expect(page.getByTestId('pnl-error')).toHaveAttribute('role', 'alert');
    await page.unroute('**/v1/reports/pnl**');
    await page.getByTestId('pnl-error-retry').click();
    await expect(page.getByTestId('pnl-row').first()).toBeVisible();
  });

  test('a garbage month in the address is replaced by a valid one without an error message', async ({ page }) => {
    await login(page);
    await page.goto('/reports/pnl?month=garbage');
    await expect(page.getByTestId('pnl-row').first().or(page.getByTestId('pnl-empty'))).toBeVisible();
    await expect(page).toHaveURL(/month=\d{4}-\d{2}/);
    await expect(page.getByTestId('pnl-error')).toHaveCount(0);
  });
});

// ================================================================== Norm
test.describe('Norm (stage 3, function 15, 20)', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openReport(page, '/reports/norm', '/v1/reports/norm', `month=${MONTH}`);
    await expect(page.getByTestId('norm')).toBeVisible();
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  const row = (key: string) => page.locator(`[data-testid="norm-row"][data-key="${key}"]`);

  test('rows carry the key, the status and the tone of the API item', async () => {
    test.skip(!api, 'no GET /v1/reports/norm call observed (mock mode)');
    const keys = await page.getByTestId('norm-row').evaluateAll((els) => els.map((e) => e.getAttribute('data-key')));
    expect(keys).toEqual(api.items.map((i: any) => i.key));
    for (const i of api.items) {
      if (i.status === undefined) {
        await expect(row(i.key), `${i.key}: a running month has no rating`).not.toHaveAttribute('data-status', /.+/);
        continue;
      }
      await expect(row(i.key), i.key).toHaveAttribute('data-status', i.status);
      await expect(row(i.key), i.key).toHaveAttribute('data-tone', i.tone);
    }
  });

  test('the write-off row is a memo row: marked, labelled, and outside the sum of shares', async () => {
    test.skip(!api, 'mock mode');
    const memoKeys = api.items.filter((i: any) => i.memo).map((i: any) => i.key);
    const marked = await page.getByTestId('norm-row').evaluateAll((els) => els.filter((e) => e.getAttribute('data-memo') === 'true').map((e) => e.getAttribute('data-key')));
    expect(marked, 'data-memo="true" exactly on the memo items').toEqual(memoKeys);
    if (!memoKeys.length) test.skip(true, 'no memo row in this response');
    for (const key of memoKeys) await expect(row(key), key).toContainText('справочно, в сумму долей не входит');
    const sum = api.items.filter((i: any) => !i.memo).reduce((acc: number, i: any) => acc + i.actual_pct.value, 0);
    expect(Math.abs(Math.round(sum * 10) / 10 - 100), 'groups + other + net profit = 100% (rounding up to 0.4)').toBeLessThanOrEqual(0.4);
    await expect(page.getByTestId('norm-open-banner')).toHaveCount(api.period.status === 'open' ? 1 : 0);
  });

  test('share, deviation in points and in roubles equal the API response', async () => {
    test.skip(!api, 'mock mode');
    for (const i of api.items) {
      expect(firstPercent(await row(i.key).getByTestId('norm-share').innerText()), `${i.key}: share`).toBe(i.actual_pct.value);
      if (i.status === 'no_norm') {
        await expect(row(i.key)).toContainText(/нормы нет/i);
        await expect(row(i.key).getByTestId('norm-gauge')).toHaveCount(0);
        continue;
      }
      const rub = await row(i.key).getByTestId('norm-deviation-rub').innerText();
      if (i.status === 'ok') expect(rub.trim()).toMatch(/^[—-]$/);
      else {
        expect(Math.abs(toKopecks(rub)), `${i.key}: rub`).toBe(Math.abs(i.deviation_rub.value));
        expect(hasMinus(rub), `${i.key}: sign of "${rub}"`).toBe(i.status === 'below');
        expect(rub.trim().startsWith('+'), `${i.key}: plus sign`).toBe(i.status === 'above');
      }
      const pp = (await row(i.key).getByTestId('norm-deviation-pp').innerText()).toLowerCase();
      const word = { ok: 'в норме', above: 'выше нормы', below: 'ниже нормы' }[i.status as 'ok' | 'above' | 'below'];
      expect(pp, `${i.key}: the deviation is said in words`).toContain(word);
      if (i.status !== 'ok') expect(Number((pp.match(/(\d+(?:[,.]\d+)?)\s*п\.п\./)?.[1] ?? 'NaN').replace(',', '.')), `${i.key}: points`).toBe(Math.abs(i.deviation_pp.value));
    }
  });

  test('the shown share minus the shown bound equals the shown deviation within 0.1 pp', async () => {
    test.skip(!api, 'mock mode');
    for (const i of api.items.filter((x: any) => x.status === 'above' || x.status === 'below')) {
      const bound = i.status === 'above' ? i.norm.max_pct : i.norm.min_pct;
      const shownPp = Math.abs(i.deviation_pp.value);
      const share = firstPercent(await row(i.key).getByTestId('norm-share').innerText());
      expect(Math.abs(Math.abs(share - bound) - shownPp), i.key).toBeLessThanOrEqual(0.1 + 1e-9);
    }
  });

  test('every share, norm, deviation and rouble amount opens a tooltip with breakdown and source', async () => {
    for (const id of ['norm-norm', 'norm-share', 'norm-deviation-pp', 'norm-deviation-rub']) {
      const els = page.locator(`[data-testid="${id}"]`);
      const n = await els.count();
      for (let i = 0; i < n; i++) {
        const el = els.nth(i);
        if (!(await el.isVisible())) continue;
        if (!(await el.getByTestId('figure-tip-trigger').count())) {
          // The no-norm row has a dash, with no numerical deviation or tooltip.
          await expect(el).toHaveText('—');
          continue;
        }
        const tip = await openTip(page, el);
        // A zero rouble deviation has an empty breakdown and the remaining margin in details.
        expect(await tip.locator('[data-testid="figure-tip-row"], [data-testid="figure-tip-detail"]').count(), `${id}[${i}]: explanation rows`).toBeGreaterThanOrEqual(1);
        expect((await tip.getByTestId('figure-tip-source').innerText()).trim().length, `${id}[${i}]: source`).toBeGreaterThan(0);
        await closeTip(page);
      }
    }
  });

  test('no money or percent value is left without a tooltip; no forbidden words', async () => {
    const offenders = await numbersWithoutTooltip(page);
    expect(offenders, `numbers without a tooltip: ${offenders.join(' | ')}`).toEqual([]);
    expect(await forbiddenWords(page)).toEqual([]);
  });

  test('export: Excel and PDF for the month on the screen', async () => {
    await downloadAndCheck(page, page.getByTestId('norm-export-xlsx'), 'norm', MONTH, 'xlsx');
    await downloadAndCheck(page, page.getByTestId('norm-export-pdf'), 'norm', MONTH, 'pdf');
  });

  test('layout: table above 1100 px, cards below; no horizontal overflow and no truncated numbers', async ({}, info) => {
    await noHorizontalOverflow(page);
    const width = info.project.use.viewport?.width ?? 1280;
    const isTable = (await page.locator('main table').count()) > 0;
    expect(isTable, width > 1100 ? 'a table on a wide screen' : 'cards on 820 and 390').toBe(width > 1100);
    const cut = await page.getByTestId('norm-share').evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth + 1).length);
    expect(cut, 'shares are not cut').toBe(0);
  });
});

test.describe('Norm states', () => {
  test('a month without revenue shows the empty card', async ({ page }) => {
    await login(page);
    await page.goto('/reports/norm?month=2000-01');
    await expect(page.getByTestId('norm-empty')).toBeVisible();
    await expect(page.getByTestId('norm-export-xlsx')).toHaveAttribute('aria-disabled', 'true');
  });
});

// ================================================================== Stock
test.describe('Stock (stage 3, function 17, 20): testids are a proposal', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openReport(page, '/reports/stock', '/v1/reports/stock', SET04 ? `as_of=${STOCK_AS_OF}` : '');
    await expect(page.getByTestId('stock')).toBeVisible();
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  const CARDS: Array<{ id: string; path: string[] }> = [
    { id: 'stock-frozen', path: ['frozen'] },
    { id: 'stock-expiring', path: ['expiring_60d'] },
    { id: 'stock-written-off', path: ['written_off_month'] },
  ];

  test('the three cards and the turnover equal the API response', async () => {
    test.skip(!api, 'no GET /v1/reports/stock call observed (mock mode)');
    for (const c of CARDS) {
      const fig = at(api, c.path);
      expect(Math.abs(toKopecks(await page.getByTestId(c.id).innerText())), c.id).toBe(Math.abs(fig.value));
    }
    const turnover = (await page.getByTestId('stock-turnover').innerText()).match(/\d+/)?.[0];
    expect(Number(turnover)).toBe(api.turnover_days.value);
  });

  test('the turnover tooltip shows the stock, the 90-day spend, the 90-day window and the norm', async () => {
    test.skip(!api, 'mock mode');
    const tip = await openTip(page, page.getByTestId('stock-turnover'));
    const text = (await tip.innerText()).replace(/[   ]/g, ' ');
    expect(text).toContain('90');
    expect(text).toContain(String(api.norm_turnover_days));
    const shown = (await tip.getByTestId('figure-tip-row').allInnerTexts()).map((t) => toKopecks(t.split('\n').pop() ?? t));
    expect(shown.slice(0, 2), 'stock and spend in the tooltip equal the API').toEqual(api.turnover_days.breakdown.slice(0, 2).map((b: any) => b.value));
    await closeTip(page);
  });

  test('expired batches are a separate figure: a banner with the amount, never in the expiring list', async () => {
    test.skip(!api, 'mock mode');
    const expired = api.expired_on_hand?.value ?? 0;
    const banner = page.getByTestId('stock-expired-banner');
    if (!expired) {
      await expect(banner, 'no expired batches: no banner').toHaveCount(0);
      return;
    }
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/истёк/i);
    expect(Math.abs(toKopecks(await page.getByTestId('stock-expired').innerText())), 'stock-expired').toBe(expired);
    const days = await page.getByTestId('stock-expiring-row').evaluateAll((els) => els.map((e) => Number(e.getAttribute('data-days-left'))));
    expect(days.every((d) => d >= 0), 'no row with days_left < 0 in the expiring list').toBe(true);
    const names = (api.expired_items ?? []).map((r: any) => r.item);
    const listed = await page.getByTestId('stock-expiring-row').allInnerTexts();
    for (const name of names) expect(listed.some((t) => t.includes(name) && /истёк|просроч/i.test(t)), `${name} is not a row of the expiring list`).toBe(false);
    const tip = await openTip(page, page.getByTestId('stock-expired'));
    expect(await tip.getByTestId('figure-tip-row').count(), 'one tooltip row per expired batch').toBeGreaterThanOrEqual(1);
    await closeTip(page);
  });

  test('the sub-lines (positions, write-off norm), the idle tabs and the write-off list equal the API', async () => {
    test.skip(!api, 'mock mode');
    if (api.frozen_positions) expect(Number((await page.getByTestId('stock-frozen-positions').innerText()).match(/\d[\d   ]*/)?.[0]?.replace(/\D/g, ''))).toBe(api.frozen_positions.value);
    if (api.written_off_norm) expect(Math.abs(toKopecks(await page.getByTestId('stock-written-off-norm').innerText()))).toBe(api.written_off_norm.value);
    const tabs = page.getByTestId('stock-idle-tab');
    if (api.idle_buckets?.length) {
      const keys = await tabs.evaluateAll((els) => els.map((e) => e.getAttribute('data-bucket')));
      expect(keys).toEqual(['all', ...api.idle_buckets.map((b: any) => b.key)]);
    }
    const rows = page.getByTestId('stock-writeoff-row');
    if (api.written_off_items) {
      await expect(rows).toHaveCount(api.written_off_items.length);
      for (let i = 0; i < api.written_off_items.length; i++) {
        expect(Math.abs(toKopecks(await rows.nth(i).getByTestId('stock-writeoff-amount').innerText())), `write-off ${i}`).toBe(api.written_off_items[i].amount.value);
      }
    }
  });

  test('the list of expiring batches follows the API order and amounts', async () => {
    test.skip(!api, 'mock mode');
    const rows = page.getByTestId('stock-expiring-row');
    await expect(rows).toHaveCount(api.expiring.length);
    const items = await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-item')));
    if (items.every((x) => x !== null)) expect(items).toEqual(api.expiring.map((r: any) => r.item));   // data-item is optional (requested, not in the spec)
    const days = await rows.evaluateAll((els) => els.map((e) => Number(e.getAttribute('data-days-left'))));
    expect(days).toEqual(api.expiring.map((r: any) => r.days_left));
    for (let i = 0; i < api.expiring.length; i++) {
      expect(Math.abs(toKopecks(await rows.nth(i).getByTestId('stock-expiring-amount').innerText()))).toBe(api.expiring[i].amount.value);
    }
  });

  test('every amount opens a tooltip with breakdown and source; the frozen tooltip has the three age buckets', async () => {
    const frozen = page.getByTestId('stock-frozen');
    const tip = await openTip(page, frozen);
    expect(await tip.getByTestId('figure-tip-row').count()).toBe(3);
    await closeTip(page);
    const offenders = await numbersWithoutTooltip(page);
    expect(offenders, `numbers without a tooltip: ${offenders.join(' | ')}`).toEqual([]);
    expect(await forbiddenWords(page)).toEqual([]);
  });

  test('export: Excel and PDF', async () => {
    await downloadAndCheck(page, page.getByTestId('stock-export-xlsx'), 'stock', null, 'xlsx');
    await downloadAndCheck(page, page.getByTestId('stock-export-pdf'), 'stock', null, 'pdf');
  });

  test('layout: no horizontal overflow', async () => {
    await noHorizontalOverflow(page);
  });
});

// ================================================================== Dashboard: "Прибыль по деньгам" (owner decision 2026-10-14)
test.describe('Dashboard profit is labelled "по деньгам" and points to the P&L report', () => {
  test('the card, the hint under the month row and the link to /reports/pnl', async ({ page }) => {
    await login(page);
    await page.goto(SET04 ? '/?as_of=2026-09-30' : '/');
    await expect(page.getByTestId('month-profit')).toBeVisible();
    const main = page.locator('main');
    await expect(main).toContainText('Прибыль по деньгам');
    await expect(main.getByText(/^Прибыль$/), 'the old bare label "Прибыль" is gone').toHaveCount(0);
    const hint = page.getByTestId('month-profit-hint');
    await expect(hint).toBeVisible();
    await expect(hint).toContainText(/по деньгам/i);
    const link = page.getByTestId('month-profit-link');
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', /\/reports\/pnl/);
    expect(await hint.innerText(), 'the hint has no figure: it is exempt from the tooltip rule').not.toMatch(/\d[\d ]*\s?(₽|%)/);
  });

  test('the tooltip of the profit says that it can differ from the net profit of the report', async ({ page }) => {
    await login(page);
    await page.goto(SET04 ? '/?as_of=2026-09-30' : '/');
    const tip = await openTip(page, page.getByTestId('month-profit'));
    const note = (await tip.getByTestId('figure-tip-note').innerText()).toLowerCase();
    expect(note).toContain('по деньгам');
    expect(note, 'taxes, amortization and the acquiring commission are not accrued here').toMatch(/налог/);
    expect(note).toMatch(/чистой прибыли/);
    await closeTip(page);
  });

  test('the link opens the P&L report of the month of the dashboard', async ({ page }) => {
    await login(page);
    await page.goto(SET04 ? '/?as_of=2026-09-30' : '/');
    await page.getByTestId('month-profit-link').click();
    await expect(page).toHaveURL(/\/reports\/pnl/);
    await expect(page.getByTestId('pnl')).toBeVisible();
    if (SET04) await expect(page).toHaveURL(/month=2026-09/);
  });
});

// ================================================================== golden set04 (to the kopeck)
test.describe('Reports on golden set04 (VF_E2E_SET04=1)', () => {
  test.skip(!SET04, 'VF_E2E_SET04=1 and a clinic seeded from tests/golden/set04 are required');
  const months: string[] = expectedAll.months.slice(0, 3);

  for (const month of months) {
    test(`P&L ${month}: every line and share equals expected.json`, async ({ page }) => {
      await login(page);
      await page.goto(`/reports/pnl?month=${month}&view=clinic`);
      await expect(page.getByTestId('pnl-row').first()).toBeVisible();
      const exp = expectedAll.pnl[month];
      const flat: Record<string, any> = {};
      for (const r of exp.rows) {
        flat[r.key] = r;
        for (const c of r.children ?? []) flat[c.key] = c;
      }
      for (const key of PNL_ROW_ORDER) {
        const text = await page.locator(`[data-testid="pnl-row-amount"][data-key="${key}"]`).innerText();
        expect(Math.abs(toKopecks(text)), `${month} ${key}`).toBe(Math.abs(flat[key].amount.value));
        expect(firstPercent(await page.locator(`[data-testid="pnl-row-share"][data-key="${key}"]`).innerText()), `${month} ${key} share`).toBe(flat[key].share_pct.value);
      }
      const net = await page.locator('[data-testid="pnl-row-amount"][data-key="net_profit"]').innerText();
      expect(hasMinus(net)).toBe(exp.net_profit < 0);
      await expect(page.locator('[data-testid="pnl-row"][data-key="obligations"]')).toContainText('Обязательства и амортизация');
    });

    test(`Norm ${month}: statuses, shares, points and roubles equal expected.json`, async ({ page }) => {
      await login(page);
      await page.goto(`/reports/norm?month=${month}`);
      await expect(page.getByTestId('norm-row').first()).toBeVisible();
      const exp = expectedAll.norm[month].items;
      const keys = await page.getByTestId('norm-row').evaluateAll((els) => els.map((e) => e.getAttribute('data-key')));
      expect(keys).toEqual(exp.map((i: any) => i.key));
      for (const i of exp) {
        const row = page.locator(`[data-testid="norm-row"][data-key="${i.key}"]`);
        await expect(row, `${month} ${i.key}`).toHaveAttribute('data-status', i.status);
        await expect(row, `${month} ${i.key}`).toHaveAttribute('data-tone', i.tone);
        expect(firstPercent(await row.getByTestId('norm-share').innerText()), `${month} ${i.key} share`).toBe(i.actual_pct);
        if (i.status === 'above' || i.status === 'below') {
          expect(Math.abs(toKopecks(await row.getByTestId('norm-deviation-rub').innerText())), `${month} ${i.key} rub`).toBe(Math.abs(i.deviation_rub));
          const pp = (await row.getByTestId('norm-deviation-pp').innerText()).replace(',', '.');
          expect(Number(pp.match(/(\d+(?:\.\d+)?)\s*п\.п\./)?.[1]), `${month} ${i.key} pp`).toBe(Math.abs(i.deviation_pp));
        }
      }
    });
  }

  test('Stock: cards, expiring batches and turnover equal expected.json', async ({ page }) => {
    await login(page);
    await page.goto(`/reports/stock?as_of=${STOCK_AS_OF}`);
    await expect(page.getByTestId('stock')).toBeVisible();
    const exp = expectedAll.stock;
    expect(Math.abs(toKopecks(await page.getByTestId('stock-frozen').innerText()))).toBe(exp.frozen.value);
    expect(Math.abs(toKopecks(await page.getByTestId('stock-expiring').innerText()))).toBe(exp.expiring_60d.value);
    expect(Math.abs(toKopecks(await page.getByTestId('stock-written-off').innerText()))).toBe(exp.written_off_month.value);
    expect(Number((await page.getByTestId('stock-turnover').innerText()).match(/\d+/)?.[0])).toBe(exp.turnover_days.value);
    const items = await page.getByTestId('stock-expiring-row').evaluateAll((els) => els.map((e) => e.getAttribute('data-item')));
    expect(items).toEqual(exp.expiring_60d.rows.map((r: any) => r.item));
    const tip = await openTip(page, page.getByTestId('stock-frozen'));
    const text = await tip.innerText();
    for (const label of Object.keys(exp.frozen.breakdown)) expect(text).toContain(label.replace('–', '–'));
    await closeTip(page);
  });

  test('Dashboard profit "по деньгам" differs from the net profit of the P&L, as the set says (alternatives.dashboard_profit)', async ({ page }) => {
    await login(page);
    await page.goto('/?as_of=2026-09-30');
    await expect(page.getByTestId('month-profit')).toBeVisible();
    const dash = toKopecks(await page.getByTestId('month-profit').innerText());
    expect(dash, 'dashboard profit = revenue minus all money out (stage-2 rule)').toBe(expectedAll.alternatives.dashboard_profit['2026-09']);
    expect(dash).not.toBe(expectedAll.pnl['2026-09'].net_profit);
  });

  for (const c of expectedAll.open_cases as Array<{ key: string; month: string; as_of: string }>) {
    const day = Number(c.as_of.slice(8));
    test(`P&L of a running month, as of ${c.as_of}: open note, period plate, lines equal expected.json`, async ({ page }) => {
      await login(page);
      await page.goto(`/reports/pnl?month=${c.month}&view=clinic&as_of=${c.as_of}`);
      await expect(page.getByTestId('pnl-row').first()).toBeVisible();
      await expect(page.getByTestId('pnl-open-note')).toBeVisible();
      await expect(page.getByTestId('pnl-period-status')).toContainText(new RegExp(`месяц идёт.*${day} сентября`, 'i'));
      if (await page.getByTestId('pnl-headline').count()) await expect(page.getByTestId('pnl-headline')).toContainText(`К ${day} сентября`);
      const exp = expectedAll.pnl[c.key];
      const flat: Record<string, any> = {};
      for (const r of exp.rows) {
        flat[r.key] = r;
        for (const ch of r.children ?? []) flat[ch.key] = ch;
      }
      for (const key of PNL_ROW_ORDER) {
        const text = await page.locator(`[data-testid="pnl-row-amount"][data-key="${key}"]`).innerText();
        expect(Math.abs(toKopecks(text)), `${c.key} ${key}`).toBe(Math.abs(flat[key].amount.value));
      }
      expect(toKopecks(await page.locator('[data-testid="pnl-row-amount"][data-key="taxes"]').innerText()), 'only the taxes already paid').toBe(0);
      await expect(page.getByTestId('pnl-open-note')).toContainText(/налоги — только уплаченные/);
    });

    test(`Norm of a running month, as of ${c.as_of}: banner, no ratings, shares equal expected.json`, async ({ page }) => {
      await login(page);
      await page.goto(`/reports/norm?month=${c.month}&as_of=${c.as_of}`);
      await expect(page.getByTestId('norm-row').first()).toBeVisible();
      await expect(page.getByTestId('norm-open-banner')).toBeVisible();
      await expect(page.getByTestId('norm-period-status')).toContainText(/месяц идёт/i);
      await expect(page.getByTestId('norm-gauge'), 'no gauge in a running month').toHaveCount(0);
      const exp = expectedAll.norm[c.key];
      const headline = (await page.getByTestId('norm-headline').innerText()).replace(/[   ]/g, ' ');
      expect(headline).toBe(exp.headline_open);
      expect(headline).not.toMatch(/выше нормы|ниже нормы/);
      const keys = await page.getByTestId('norm-row').evaluateAll((els) => els.map((e) => e.getAttribute('data-key')));
      expect(keys).toEqual(exp.items.map((i: any) => i.key));
      for (const i of exp.items) {
        const row = page.locator(`[data-testid="norm-row"][data-key="${i.key}"]`);
        await expect(row, `${i.key}: no data-status`).not.toHaveAttribute('data-status', /.+/);
        expect(firstPercent(await row.getByTestId('norm-share').innerText()), `${c.key} ${i.key} share`).toBe(i.actual_pct);
        for (const id of ['norm-deviation-pp', 'norm-deviation-rub']) {
          const cell = row.getByTestId(id);
          if (await cell.count()) expect((await cell.first().innerText()).trim(), `${i.key}: ${id} is a dash`).toMatch(/^[—-]$/);
        }
        await expect(row.getByText(/выше нормы|ниже нормы|в норме/i)).toHaveCount(0);
      }
    });
  }

  test('Norm of a closed month has no open banner; P&L of a closed month has no open note', async ({ page }) => {
    await login(page);
    await page.goto(`/reports/norm?month=${MONTH}`);
    await expect(page.getByTestId('norm-row').first()).toBeVisible();
    await expect(page.getByTestId('norm-open-banner')).toHaveCount(0);
    await page.goto(`/reports/pnl?month=${MONTH}`);
    await expect(page.getByTestId('pnl-row').first()).toBeVisible();
    await expect(page.getByTestId('pnl-open-note')).toHaveCount(0);
  });

  test('Norm: the write-off row is a memo row with the amount of the expired write-offs', async ({ page }) => {
    await login(page);
    await page.goto(`/reports/norm?month=${MONTH}`);
    const row = page.locator('[data-testid="norm-row"][data-key="writeoff"]');
    await expect(row).toHaveAttribute('data-memo', 'true');
    await expect(row).toContainText('справочно, в сумму долей не входит');
    const exp = expectedAll.norm[MONTH].items.find((i: any) => i.key === 'writeoff');
    expect(firstPercent(await row.getByTestId('norm-share').innerText())).toBe(exp.actual_pct);
    expect(Math.abs(toKopecks(await row.getByTestId('norm-deviation-rub').innerText()))).toBe(exp.deviation_rub);
    await expect(page.locator('[data-testid="norm-row"][data-memo="true"]')).toHaveCount(1);
  });

  test('Stock: expired batches, positions, idle tabs, write-offs and the write-off norm equal expected.json', async ({ page }) => {
    await login(page);
    await page.goto(`/reports/stock?as_of=${STOCK_AS_OF}`);
    await expect(page.getByTestId('stock')).toBeVisible();
    const exp = expectedAll.stock;
    await expect(page.getByTestId('stock-expired-banner')).toBeVisible();
    expect(Math.abs(toKopecks(await page.getByTestId('stock-expired').innerText())), 'expired on the shelf').toBe(exp.expired_on_hand.value);
    const days = await page.getByTestId('stock-expiring-row').evaluateAll((els) => els.map((e) => Number(e.getAttribute('data-days-left'))));
    expect(days, 'the expiring list: 0 ... 60 days, no expired batch').toEqual(exp.expiring_60d.rows.map((r: any) => r.days_left));
    expect(Number((await page.getByTestId('stock-frozen-positions').innerText()).match(/\d+/)?.[0])).toBe(exp.frozen_positions.value);
    expect(Math.abs(toKopecks(await page.getByTestId('stock-written-off-norm').innerText())), 'norm of the write-off: 0.8% of the September revenue').toBe(exp.written_off_norm.value);
    const wrows = page.getByTestId('stock-writeoff-row');
    await expect(wrows).toHaveCount(exp.written_off_items.length);
    for (let i = 0; i < exp.written_off_items.length; i++) {
      expect(Math.abs(toKopecks(await wrows.nth(i).getByTestId('stock-writeoff-amount').innerText())), `write-off ${i}`).toBe(exp.written_off_items[i].amount);
    }
    expect(await page.getByTestId('stock-idle-tab').evaluateAll((els) => els.map((e) => e.getAttribute('data-bucket')))).toEqual(['all', '60_89', '90_179', '180_plus']);
    await expect(page.getByTestId('stock-idle-row')).toHaveCount(exp.idle_pages.find((p: any) => p.bucket === 'all' && p.limit === 10).total);
    await expect(page.getByTestId('stock-idle-more'), 'six positions fit one page of ten').toHaveCount(0);
    await page.locator('[data-testid="stock-idle-tab"][data-bucket="180_plus"]').click();
    const page180 = exp.idle_pages.find((p: any) => p.bucket === '180_plus' && p.limit === 10);
    await expect(page.getByTestId('stock-idle-row')).toHaveCount(page180.total);
    const amounts = await page.getByTestId('stock-idle-amount').allInnerTexts();
    expect(amounts.map((t) => Math.abs(toKopecks(t)))).toEqual(page180.pages[0].items.map((i: any) => i.amount));
  });
});
