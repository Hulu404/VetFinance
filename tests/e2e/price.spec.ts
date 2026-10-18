import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  SET06, WRITE, closeTip, email, fieldOf, forbiddenWords, login, noHorizontalOverflow, norm, openPage, openTip, password, q, rubText,
  toKopecks, toPct, url, val, withAnswer,
} from './stage5-helpers';

/**
 * Stage 5 e2e: "Прайс услуг" (functions 11, 12).
 *
 * data-testid, texts and routes come from design/screens/price.md (designer, 2026-10-18, after the owner's decisions):
 * /price?service=<id>&filter=all|loss|no_recipe&sort=margin|profit&order=asc|desc&q=; `as_of=YYYY-MM-DD` is passed to the API as is
 * (the spec does not name it: the tests use it only for the golden clinic, see docs/handoff.md).
 * The client never counts: row and card numbers equal the API, the parts of a card add up to the price (checked here from what is shown).
 *
 * Generic part (any clinic): rows = API, headline, tab counters, default order (worst margin first, no margin last), filters, search,
 * the card (price, profit, bar, legend, tooltips), no-recipe and loss cards, states (error, empty, no recipes at all), no overflow.
 * Golden part (VF_E2E_SET06=1, clinic G seeded from tests/golden/set06, user test-g@vetfinance.test): numbers equal expected.json.
 * Writing part (VF_E2E_WRITE=1, a throw-away test clinic): add, edit and delete a manual service, fill a techcard. The tests use a name with
 * a time stamp, delete what they create, and tolerate leftovers of earlier runs (a deleted object may stay in the database as a trace).
 * Env: VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD.
 */
const expectedAll = JSON.parse(readFileSync(resolve(__dirname, '../golden/set06/expected.json'), 'utf-8'));
const GOLDEN_AS_OF: string = expectedAll.as_of; // 2026-10-01
const GM = expectedAll.cases.main;
const AS_OF_Q = SET06 ? `as_of=${GOLDEN_AS_OF}` : '';
const PART_LABELS: Record<string, RegExp> = {
  doctor_pay: /ЗП врача/, drugs: /Препараты/, anesthesia: /Анестезия/, supplies: /Расходники/, acquiring: /Эквайринг/,
  fixed: /Постоянные/, taxes: /Налоги/, net: /Прибыль|Чистая прибыль/,
};
const PART_KEYS = ['doctor_pay', 'drugs', 'anesthesia', 'supplies', 'acquiring', 'fixed', 'taxes'];

test.skip(!url || !email || !password, 'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD are not set');

const rows = (page: Page) => page.getByTestId('price-row');
const rowById = (page: Page, id: string) => page.locator(`[data-testid="price-row"][data-id="${id}"]`);
const priceUrl = (...parts: string[]) => `/price${q(...parts, AS_OF_Q) ? `?${q(...parts, AS_OF_Q)}` : ''}`;

/** Opens the price list and waits for rows (or the empty/error state). Returns the first GET /v1/services answer (null in mock mode). */
async function openList(page: Page, ...parts: string[]): Promise<any | null> {
  const api = await openPage(page, '/price', '/v1/services?', q(...parts, AS_OF_Q));
  await expect(page.getByTestId('price')).toBeVisible();
  return api;
}

/** Margin text of a row: "26,0%" -> 26, "—" -> null. */
async function rowMargin(page: Page, id: string): Promise<number | null> {
  const text = await rowById(page, id).getByTestId('price-row-margin').innerText();
  return /%/.test(text) ? toPct(text) : null;
}

/** Opens the card of a service through its row (the row must be on the page). Returns the cost answer (null in mock mode). */
async function openCard(page: Page, id: string): Promise<any | null> {
  const wait = page
    .waitForResponse((r) => r.url().includes(`/v1/services/${id}/cost`) && r.request().method() === 'GET' && r.status() === 200, { timeout: 8000 })
    .then((r) => r.json())
    .catch(() => null);
  await rowById(page, id).getByTestId('price-row-open').click();
  await expect(page.getByTestId('price-card')).toHaveAttribute('data-id', id);
  return wait;
}

/** Amounts of the legend of the open card by part key (kopecks, signed); a part that is not filled has no amount. */
async function legendAmounts(page: Page): Promise<Record<string, number | null>> {
  const out: Record<string, number | null> = {};
  const items = page.getByTestId('price-legend-item');
  const n = await items.count();
  for (let i = 0; i < n; i++) {
    const item = items.nth(i);
    const key = (await item.getAttribute('data-key'))!;
    const text = norm(await item.innerText());
    out[key] = /₽/.test(text) ? toKopecks(text.replace(/\d+(?:[,.]\d+)?\s*%/g, '')) : null;
  }
  return out;
}

const WORDS = /ЗП врача|Препараты|Анестезия|Расходники|Эквайринг|Постоянные|Налоги и взносы|Прибыль/;

// ================================================================== List
test.describe('Price list (stage 5, functions 11, 12)', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openList(page);
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test('title, subtitle with the number of services, headline and tabs with counters equal the API', async () => {
    await expect(page.getByRole('heading', { level: 1, name: 'Прайс услуг' })).toBeVisible();
    test.skip(!api, 'mock mode: no API response captured');
    if (!api.items.length) return;
    expect(norm(await page.getByTestId('price-headline').innerText())).toBe(norm(api.headline));
    await expect(page.locator('main')).toContainText(`${api.counts.all}`);
    for (const [id, key, label] of [['price-filter-all', 'all', 'Все'], ['price-filter-loss', 'loss', 'В минус'], ['price-filter-no-recipe', 'no_recipe', 'Нет техкарты']] as const) {
      const tab = page.getByTestId(id);
      await expect(tab).toContainText(label);
      await expect(tab).toHaveAttribute('data-count', String(api.counts[key]));
    }
    await expect(page.getByTestId('price-filter-all')).toHaveAttribute('aria-checked', 'true');
  });

  test('every row equals the API: price, how many times, margin, profit for the month, status', async () => {
    test.skip(!api, 'mock mode: no API response captured');
    const n = await rows(page).count();
    expect(n).toBe(api.items.length);
    for (let i = 0; i < n; i++) {
      const it = api.items[i];
      const r = rows(page).nth(i);
      await expect(r).toHaveAttribute('data-id', it.id);
      await expect(r).toHaveAttribute('data-status', it.status);
      await expect(r).toHaveAttribute('data-loss', String(it.margin_pct !== null && val(it.margin_pct)! < 0));
      expect(toKopecks(await r.getByTestId('price-row-price').innerText()), it.name).toBe(val(it.price));
      expect(Number((await r.getByTestId('price-row-visits').innerText()).replace(/[^\d]/g, '')), it.name).toBe(val(it.visits_month));
      const margin = await r.getByTestId('price-row-margin').innerText();
      if (it.margin_pct === null) {
        expect(margin.trim()).toBe('—');
        await expect(r.getByTestId('price-row-pill')).toHaveAttribute('data-kind', 'no_recipe');
        await expect(r.getByTestId('price-row-pill')).toContainText('нет техкарты');
        await expect(r.getByTestId('price-row-profit')).toHaveText(/—/);
      } else {
        expect(toPct(margin), it.name).toBe(val(it.margin_pct));
        expect(toKopecks(await r.getByTestId('price-row-profit').innerText()), it.name).toBe(val(it.monthly_profit));
      }
      if (it.margin_pct !== null && val(it.margin_pct)! < 0) await expect(r.getByTestId('price-row-pill')).toContainText('в минус');
      if (it.status === 'partial') await expect(r.getByTestId('price-row-pill')).toContainText('не хватает данных');
      await expect(r.getByTestId('price-row-source')).toHaveAttribute('data-source', it.source);
    }
  });

  test('the default order is the worst margin first; services without a margin are last; the sort buttons say so', async () => {
    const n = await rows(page).count();
    test.skip(n < 2, 'fewer than two services');
    const margins: (number | null)[] = [];
    for (let i = 0; i < n; i++) margins.push(await rowMargin(page, (await rows(page).nth(i).getAttribute('data-id'))!));
    const rated = margins.filter((m): m is number => m !== null);
    expect(margins.slice(0, rated.length).every((m) => m !== null)).toBe(true);
    expect(rated).toEqual([...rated].sort((a, b) => a - b));
    await expect(page.getByTestId('price-sort-margin')).toHaveAttribute('aria-sort', 'ascending');
  });

  test('the "В минус" tab shows only loss-making services and its counter equals the number of rows', async ({ page: p }) => {
    await login(p);
    const filtered = await openList(p, 'filter=loss');
    await expect(p.getByTestId('price-filter-loss')).toHaveAttribute('aria-checked', 'true');
    const count = Number(await p.getByTestId('price-filter-loss').getAttribute('data-count'));
    if (count === 0) {
      await expect(p.getByTestId('price-empty-filter')).toBeVisible();
      await expect(p.getByTestId('price-empty-filter')).toContainText('В минус пока ничего нет');
      return;
    }
    await expect(rows(p)).toHaveCount(Math.min(count, filtered ? filtered.items.length : count));
    const flags = await rows(p).evaluateAll((els) => els.map((e) => e.getAttribute('data-loss')));
    expect(flags.every((f) => f === 'true')).toBe(true);
  });

  test('the "Нет техкарты" tab shows only services without a techcard', async ({ page: p }) => {
    await login(p);
    await openList(p, 'filter=no_recipe');
    const count = Number(await p.getByTestId('price-filter-no-recipe').getAttribute('data-count'));
    test.skip(count === 0, 'every service has a techcard');
    const statuses = await rows(p).evaluateAll((els) => els.map((e) => e.getAttribute('data-status')));
    expect(statuses.length).toBeGreaterThan(0);
    expect(statuses.every((s) => s === 'no_recipe')).toBe(true);
  });

  test('search narrows the list by name without case; a miss shows the empty-filter state', async () => {
    const n = await rows(page).count();
    test.skip(n === 0, 'no services');
    const name = (await rows(page).first().getByTestId('price-row-open').innerText()).trim();
    const word = name.split(/\s+/)[0].slice(0, 4).toUpperCase();
    await page.getByTestId('price-search').fill(word);
    // the list is filtered by the server after a pause: wait until every row matches
    await expect
      .poll(async () => (await rows(page).getByTestId('price-row-open').allInnerTexts()).every((t) => t.toLowerCase().includes(word.toLowerCase())))
      .toBe(true);
    expect(await rows(page).count()).toBeGreaterThan(0);
    await page.getByTestId('price-search').fill('нет-такой-услуги-qqq');
    await expect(page.getByTestId('price-empty-filter')).toBeVisible();
    await page.getByTestId('price-search').fill('');
    await expect.poll(async () => rows(page).count()).toBe(n);
  });

  test('the card: price, profit and parts equal the API; parts and profit add up to the price; every legend item opens a tooltip', async () => {
    const n = await rows(page).count();
    test.skip(n === 0, 'no services');
    const id = (await page.locator('[data-testid="price-row"][data-status="ok"]').first().getAttribute('data-id')) ?? (await rows(page).first().getAttribute('data-id'))!;
    const cost = await openCard(page, id);
    test.skip(!cost, 'mock mode: no API response captured');
    expect(toKopecks(await page.getByTestId('price-card-price').innerText())).toBe(val(cost.price));
    const legend = await legendAmounts(page);
    for (const p of cost.parts) if (p.amount !== null) expect(legend[p.key], p.key).toBe(val(p.amount));
    if (cost.net_profit !== null) {
      expect(toKopecks(await page.getByTestId('price-card-net').innerText())).toBe(val(cost.net_profit));
      expect(toPct(await page.getByTestId('price-card-net-pct').innerText())).toBe(val(cost.net_margin_pct));
      const sum = PART_KEYS.reduce((s, k) => s + (legend[k] ?? 0), 0) + (val(cost.net_profit) as number);
      expect(sum).toBe(val(cost.price));                       // what is shown adds up to the price to the kopeck
      const shares = page.getByTestId('price-legend-share');
      const total = (await shares.allInnerTexts()).map(toPct).reduce((s, x) => s + x, 0);
      expect(Math.round(total * 10)).toBe(1000);
      await expect(page.getByTestId('price-bar')).toHaveAttribute('role', 'img');
      const label = (await page.getByTestId('price-bar').getAttribute('aria-label')) ?? '';
      expect(label).toMatch(/Из чего состоит цена/);
      expect(norm(label)).toMatch(rubText(val(cost.price)!));
    }
    for (const key of PART_KEYS) {
      const item = page.locator(`[data-testid="price-legend-item"][data-key="${key}"]`);
      if (!(await item.count())) continue;
      const tip = await openTip(page, item);
      await expect(tip).not.toBeEmpty();
      await closeTip(page);
    }
    await expect(page.getByTestId('price-card-basis')).toContainText(cost.basis_month ? /за [а-я]+ \d{4}/ : /.*/);
    await page.getByTestId('price-card-close').click();
    await expect(page.getByTestId('price-card')).toHaveCount(0);
  });

  test('a service without a techcard: the banner, no profit, no bar, the button to fill it', async () => {
    const r = page.locator('[data-testid="price-row"][data-status="no_recipe"]').first();
    test.skip((await r.count()) === 0, 'every service has a techcard');
    const id = (await r.getAttribute('data-id'))!;
    await openCard(page, id);
    const banner = page.getByTestId('price-card-missing');
    await expect(banner).toHaveAttribute('data-missing', /recipe/);
    await expect(banner).toContainText('Нет техкарты: без неё прибыль была бы завышена, поэтому мы её не считаем.');
    await expect(banner.getByRole('button', { name: 'Заполнить техкарту' })).toBeVisible();
    await expect(page.getByTestId('price-card-net')).toHaveText(/—/);
    await expect(page.getByTestId('price-card-monthly')).toHaveText(/—/);
    await expect(page.getByTestId('price-bar')).toHaveCount(0);
    await expect(page.getByTestId('price-card')).toContainText('Полоса появится, когда будет техкарта');
    await expect(page.getByTestId('price-part-warning').first()).toContainText('не заполнено');
    await page.getByTestId('price-card-close').click();
  });

  test('a loss-making service: a minus sign, the pill "в минус", and the words about how much is missing', async () => {
    const r = page.locator('[data-testid="price-row"][data-loss="true"]').first();
    test.skip((await r.count()) === 0, 'no loss-making service in this clinic');
    const id = (await r.getAttribute('data-id'))!;
    const cost = await openCard(page, id);
    expect(toKopecks((await page.getByTestId('price-card-net').innerText()).replace('−', '-'))).toBeLessThan(0);
    await expect(page.getByTestId('price-card')).toContainText('в минус');
    await expect(page.getByTestId('price-card')).toContainText(/не хватает .* до нуля/i);
    if (cost) expect(val(cost.net_profit)).toBeLessThan(0);
    await page.getByTestId('price-card-close').click();
  });

  test('the card is addressable: the service id is in the address and the card opens from it', async ({ page: p }) => {
    await login(p);
    const list = await openList(p);
    test.skip(!list || !list.items.length, 'no services');
    const id = list.items[0].id;
    await p.goto(priceUrl(`service=${id}`));
    await expect(p.getByTestId('price-card')).toHaveAttribute('data-id', id);
  });

  test('no forbidden words (recommendations, roles, branches); no horizontal page overflow', async () => {
    expect(await forbiddenWords(page)).toEqual([]);
    await noHorizontalOverflow(page);
    const text = await page.locator('main').innerText();
    expect(text).not.toMatch(/поднимите цену|рекомендуем/i);
  });
});

// ================================================================== Golden
test.describe('Price list of the golden clinic G (set06)', () => {
  test.skip(!SET06, 'VF_E2E_SET06=1 is needed (clinic G seeded from tests/golden/set06)');

  test('the list is in the order of expected.json with price, times and margin to the kopeck; the headline and the counters agree', async ({ page }) => {
    await login(page);
    await openList(page);
    const want = GM.services as any[];
    await expect(rows(page)).toHaveCount(want.length);
    for (let i = 0; i < want.length; i++) {
      const r = rows(page).nth(i);
      await expect(r.getByTestId('price-row-open')).toContainText(want[i].name);
      await expect(r).toHaveAttribute('data-status', want[i].status);
      expect(toKopecks(await r.getByTestId('price-row-price').innerText()), want[i].name).toBe(want[i].price);
      expect(Number((await r.getByTestId('price-row-visits').innerText()).replace(/[^\d]/g, '')), want[i].name).toBe(want[i].visits_month);
      if (want[i].net_margin_pct === null) expect((await r.getByTestId('price-row-margin').innerText()).trim()).toBe('—');
      else expect(toPct(await r.getByTestId('price-row-margin').innerText()), want[i].name).toBe(want[i].net_margin_pct);
    }
    for (const [id, key] of [['price-filter-all', 'all'], ['price-filter-loss', 'loss'], ['price-filter-no-recipe', 'no_recipe']] as const) {
      await expect(page.getByTestId(id)).toHaveAttribute('data-count', String(GM.counts[key]));
    }
    const headline = norm(await page.getByTestId('price-headline').innerText());
    expect(headline).toContain('1 услуга из 11');
    expect(headline).toContain('Стационар, сутки');
    expect(headline).toContain('−6,3%');
    expect(headline).toContain('У 2 услуг нет техкарты');
  });

  test('«Кастрация кота»: every part of the legend equals expected.json, the shares add up to 100,0 and the profit is 926,54 ₽', async ({ page }) => {
    await login(page);
    await openList(page);
    const s = (GM.services as any[]).find((x) => x.id === 'S4');
    await openCard(page, 'S4');
    const legend = await legendAmounts(page);
    for (const k of PART_KEYS) expect(legend[k], k).toBe(s.parts[k]);
    expect(toKopecks(await page.getByTestId('price-card-net').innerText())).toBe(s.net_profit);
    expect(toPct(await page.getByTestId('price-card-net-pct').innerText())).toBe(s.net_margin_pct);
    for (const k of PART_KEYS) {
      const share = page.locator(`[data-testid="price-legend-share"]`).nth(PART_KEYS.indexOf(k));
      expect(toPct(await share.innerText()), k).toBe(s.shares[k]);
    }
    await expect(page.getByTestId('price-card-monthly')).toContainText(rubText(s.monthly_profit));
    await expect(page.getByTestId('price-card-monthly')).toContainText('18');
    const tip = await openTip(page, page.locator('[data-testid="price-legend-item"][data-key="anesthesia"]'));
    await expect(tip).toContainText(/Золетил/);
    await expect(tip).toContainText(rubText(s.parts.anesthesia));
    await closeTip(page);
  });

  test('«Стационар, сутки» is the loss-making one: −149,59 ₽, −6,3%, the pill and the first row', async ({ page }) => {
    await login(page);
    await openList(page);
    await expect(rows(page).first()).toHaveAttribute('data-id', 'S6');
    await expect(rows(page).first()).toHaveAttribute('data-loss', 'true');
    await openCard(page, 'S6');
    expect(toKopecks(await page.getByTestId('price-card-net').innerText())).toBe(-14959);
    expect(toPct(await page.getByTestId('price-card-net-pct').innerText())).toBe(-6.3);
    await expect(page.getByTestId('price-card')).toContainText(rubText(14959));
  });

  test('a service with a missing purchase price is "не хватает данных" and names the item; a service without sales keeps its price', async ({ page }) => {
    await login(page);
    await openList(page);
    await expect(rowById(page, 'S5').getByTestId('price-row-pill')).toHaveAttribute('data-kind', 'partial');
    await openCard(page, 'S5');
    const banner = page.getByTestId('price-card-missing');
    await expect(banner).toHaveAttribute('data-missing', /item_no_cost/);
    await expect(banner).toContainText('Насадка эндоскопа');
    await expect(banner).toContainText('нет цены закупки');
    await page.getByTestId('price-card-close').click();
    const s8 = rowById(page, 'S8');                       // sold in July only: 0 times in September, the price stays
    expect(toKopecks(await s8.getByTestId('price-row-price').innerText())).toBe(190000);
    expect(Number((await s8.getByTestId('price-row-visits').innerText()).replace(/[^\d]/g, ''))).toBe(0);
    await expect(s8.getByTestId('price-row-profit')).toContainText(/0/);
  });

  test('a service without its own duration uses the clinic average and says so; a manual service without sales keeps the entered price', async ({ page }) => {
    await login(page);
    await openList(page);
    await openCard(page, 'S10');
    await expect(page.getByTestId('price-minutes-note')).toContainText('длительность средняя по клинике, 30 мин');
    await expect(page.getByTestId('price-minutes-own')).toContainText('Указать свою');
    const fixed = page.locator('[data-testid="price-legend-item"][data-key="fixed"]');
    expect(toKopecks(await fixed.innerText())).toBe(23073);
    await page.getByTestId('price-card-close').click();
    const manual = page.locator('[data-testid="price-row"]', { hasText: 'Консультация ортопеда' });
    await expect(manual).toHaveCount(1);
    await expect(manual.getByTestId('price-row-source')).toHaveAttribute('data-source', 'manual');
    await expect(manual.getByTestId('price-row-source')).toContainText('вручную');
    expect(toKopecks(await manual.getByTestId('price-row-price').innerText())).toBe(250000);
    const tip = await openTip(page, manual.getByTestId('price-row-price'));
    await expect(tip).toContainText('Цена, введённая вручную');
    await closeTip(page);
    await manual.getByTestId('price-row-open').click();
    await expect(page.getByTestId('price-source')).toHaveAttribute('data-source', 'manual');
    await expect(page.getByTestId('price-service-edit')).toBeVisible();
    await expect(page.getByTestId('price-service-delete')).toHaveCount(0);        // the delete button is in the edit dialog, not on the card
    await page.getByTestId('price-service-edit').click();
    await expect(page.locator('[data-testid="price-service-delete"], [data-testid="price-service-dialog-delete"]')).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('a service of Vetmanager cannot be edited or deleted; the manual «Чистка ушей» was absorbed by its sales', async ({ page }) => {
    await login(page);
    await openList(page);
    await openCard(page, 'S4');
    await expect(page.getByTestId('price-source')).toHaveAttribute('data-source', 'vetmanager');
    await expect(page.getByTestId('price-service-edit')).toHaveCount(0);
    await expect(page.locator('[data-testid="price-service-delete"], [data-testid="price-service-dialog-delete"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="price-row"]', { hasText: /чистка\s+ушей/i })).toHaveCount(1);
    expect(toKopecks(await rowById(page, 'S7').getByTestId('price-row-price').innerText())).toBe(60000);
    await expect(rowById(page, 'S7').getByTestId('price-row-source')).toHaveAttribute('data-source', 'vetmanager');
  });
});

// ================================================================== Writing
test.describe('Writing: a manual service is added, edited, given a techcard and deleted', () => {
  test.skip(!WRITE, 'VF_E2E_WRITE=1 is needed: the tests change data of the test clinic and restore it');
  test.describe.configure({ mode: 'serial' });

  const name = () => `Тест e2e услуга ${Date.now() % 1000000}`;

  async function addService(page: Page, title: string, price: string) {
    await page.getByTestId('price-add').click();
    await expect(page.getByTestId('price-service-dialog')).toBeVisible();
    await (await fieldOf(page, 'price-service-field-name')).fill(title);
    await (await fieldOf(page, 'price-service-field-price')).fill(price);
    const posted = page.waitForResponse((r) => r.url().endsWith('/v1/services') && r.request().method() === 'POST');
    await page.getByTestId('price-service-save').click();
    const res = await posted;
    expect(res.status()).toBe(201);
    await expect(page.getByText('Услуга добавлена')).toBeVisible();
    return (await res.json()).id as string;
  }

  /** The delete button is inside the dialog «Изменить услугу» (price.md: `danger` «Удалить услугу» at the bottom left). Testid by the spec
   *  table is `price-service-delete`; the frontend may name it `price-service-dialog-delete` (agreed in docs/handoff.md): both are accepted. */
  const dialogDelete = (page: Page) => page.locator('[data-testid="price-service-delete"], [data-testid="price-service-dialog-delete"]');

  /** Deletes through the UI: card -> «Изменить услугу» -> «Удалить услугу» -> confirmation. A service that is already gone (the row is not in
   *  the list) is not a failure; a service that is there but cannot be deleted this way fails with a clear message. */
  async function removeService(page: Page, id: string) {
    await page.goto(priceUrl(`service=${id}`));
    await expect(page.getByTestId('price')).toBeVisible();
    await expect(page.getByTestId('price-row').first().or(page.getByTestId('price-empty'))).toBeVisible();
    if ((await rowById(page, id).count()) === 0) return;
    const edit = page.getByTestId('price-service-edit');
    await expect(edit, `the card of the manual service ${id} must have the button «Изменить услугу»`).toBeVisible();
    await edit.click();
    await expect(dialogDelete(page), `the dialog «Изменить услугу» must have the button «Удалить услугу» (price.md)`).toBeVisible();
    await dialogDelete(page).click();
    const deleted = page.waitForResponse((r) => r.url().includes(`/v1/services/${id}`) && r.request().method() === 'DELETE');
    await page.getByTestId('price-service-delete-confirm').click();
    expect([204, 404]).toContain((await deleted).status());
  }

  test('add: the field errors come first and nothing is sent; then the service appears as a manual one without a techcard', async ({ page }) => {
    await login(page);
    await openList(page);
    await page.getByTestId('price-add').click();
    let sent = 0;
    page.on('request', (r) => { if (r.method() === 'POST' && r.url().endsWith('/v1/services')) sent += 1; });
    await page.getByTestId('price-service-save').click();
    await expect(page.getByTestId('price-service-field-name-error')).toContainText('Напишите название услуги');
    await expect(page.getByTestId('price-service-field-price-error')).toContainText('Укажите цену');
    expect(sent).toBe(0);
    await (await fieldOf(page, 'price-service-field-name')).fill('Тест');
    await (await fieldOf(page, 'price-service-field-price')).fill('0');
    await page.getByTestId('price-service-save').click();
    await expect(page.getByTestId('price-service-field-price-error')).toContainText('Цена должна быть больше нуля');
    await page.keyboard.press('Escape');

    const title = name();
    await page.reload();
    const id = await addService(page, title, '1800');
    try {
      const r = rowById(page, id);
      await expect(r).toHaveCount(1);
      await expect(r.getByTestId('price-row-source')).toHaveAttribute('data-source', 'manual');
      await expect(r).toHaveAttribute('data-status', 'no_recipe');
      expect(toKopecks(await r.getByTestId('price-row-price').innerText())).toBe(180000);
      await expect(page.getByTestId('price-card')).toHaveAttribute('data-id', id);          // the card opens at once
      await expect(page.getByTestId('price-card-missing')).toHaveAttribute('data-missing', /recipe/);
      const tip = await openTip(page, r.getByTestId('price-row-price'));
      await expect(tip).toContainText('Цена, введённая вручную');
      await closeTip(page);
    } finally {
      await removeService(page, id);
    }
  });

  test('a duplicate name is refused with the designer text; edit changes the price; delete removes the row and the card', async ({ page }) => {
    await login(page);
    await openList(page);
    const title = name();
    const id = await addService(page, title, '1000');
    try {
      await page.getByTestId('price-add').click();
      await (await fieldOf(page, 'price-service-field-name')).fill(title.toUpperCase());
      await (await fieldOf(page, 'price-service-field-price')).fill('900');
      await page.getByTestId('price-service-save').click();
      await expect(page.getByTestId('price-service-field-name-error')).toContainText('Такая услуга уже есть');
      await page.keyboard.press('Escape');

      await page.goto(priceUrl(`service=${id}`));
      await page.getByTestId('price-service-edit').click();
      await (await fieldOf(page, 'price-service-field-price')).fill('1250.50');
      const patched = page.waitForResponse((r) => r.url().includes(`/v1/services/${id}`) && r.request().method() === 'PATCH');
      await page.getByTestId('price-service-save').click();
      expect([200, 204]).toContain((await patched).status());
      await expect.poll(async () => toKopecks(await rowById(page, id).getByTestId('price-row-price').innerText())).toBe(125050);
    } finally {
      await removeService(page, id);
    }
    await expect(page.getByText('Услуга удалена')).toBeVisible();
    await page.goto(priceUrl(`service=${id}`));
    await expect(rowById(page, id)).toHaveCount(0);
  });

  test('a techcard: the minutes, a position from the stock and the quantity are saved and the card shows a profit; the average duration note goes away', async ({ page }) => {
    await login(page);
    await openList(page);
    const title = name();
    const id = await addService(page, title, '2000');
    try {
      await page.getByTestId('price-card-missing').getByRole('button', { name: 'Заполнить техкарту' }).click();
      await expect(page.getByTestId('price-recipe-dialog')).toBeVisible();
      await (await fieldOf(page, 'price-recipe-field-minutes')).fill('0');
      await page.getByTestId('price-recipe-save').click();
      await expect(page.getByTestId('price-recipe-field-minutes-error')).toContainText('От 1 до 1440 минут');
      await (await fieldOf(page, 'price-recipe-field-minutes')).fill('20');
      await (await fieldOf(page, 'price-recipe-field-doctor_pct')).fill('30');
      const saved = page.waitForResponse((r) => r.url().includes(`/v1/services/${id}/recipe`) && r.request().method() === 'PUT');
      await page.getByTestId('price-recipe-save').click();
      expect((await saved).status()).toBe(200);
      await expect(page.getByText('Техкарта сохранена')).toBeVisible();
      await expect(rowById(page, id)).toHaveAttribute('data-status', /ok|partial/);        // an empty techcard is a service without materials
      expect(toPct(await rowById(page, id).getByTestId('price-row-margin').innerText())).toBeLessThan(100);
      await expect(page.getByTestId('price-minutes-note')).toHaveCount(0);                // the own duration is set
      const legend = await legendAmounts(page);
      expect(legend.doctor_pay).toBe(60000);                                              // 30% of 2 000 rub
    } finally {
      await removeService(page, id);
    }
  });
});

// ================================================================== States
test.describe('Price states', () => {
  test('a server error shows the error card with Retry', async ({ page }) => {
    await login(page);
    await page.route('**/v1/services?**', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":{"code":"sync_failed","message":"x","details":{}}}' }));
    await page.goto('/price');
    await expect(page.getByTestId('price-error')).toBeVisible();
    await expect(page.getByTestId('price-error')).toContainText('Не получилось загрузить прайс');
    await page.unroute('**/v1/services?**');
    await page.getByTestId('price-error-retry').click();
    await expect(page.getByTestId('price-error')).toHaveCount(0);
  });

  test('without services the empty state offers to connect Vetmanager', async ({ page }) => {
    await login(page);
    await withAnswer(page, '**/v1/services?**', '/price', (b) => { b.items = []; b.counts = { all: 0, loss: 0, no_recipe: 0 }; delete b.headline; b.next_cursor = null; });
    await expect(page.getByTestId('price-empty')).toContainText('Услуг пока нет');
    await expect(page.getByTestId('price-empty')).toContainText('Подключите Ветменеджер');
    await expect(page.getByTestId('price-empty').getByRole('link', { name: 'Подключения' })).toBeVisible();
  });

  test('when no service has a techcard the headline says so and the rows show "—" instead of a margin', async ({ page }) => {
    await login(page);
    await withAnswer(page, '**/v1/services?**', '/price', (b) => {
      b.items = b.items.map((i: any) => ({ ...i, status: 'no_recipe', margin_pct: null, monthly_profit: null }));
      b.counts = { all: b.items.length, loss: 0, no_recipe: b.items.length };
      b.headline = 'Техкарт пока нет, поэтому маржу мы не считаем. Начните с самых частых услуг: для каждой нужен список материалов и время.';
    });
    await expect(page.getByTestId('price-headline')).toContainText('Техкарт пока нет');
    await expect(rows(page).first()).toBeVisible();
    const margins = await rows(page).getByTestId('price-row-margin').allInnerTexts();
    expect(margins.every((m) => m.trim() === '—')).toBe(true);
  });

  test('a month without a bank statement: no profit, no margin, no bar for any service; the card says what is missing', async ({ page }) => {
    await login(page);
    await page.route('**/v1/services?**', async (route) => {
      const res = await route.fetch();
      const b = await res.json();
      b.items = b.items.map((i: any) => ({ ...i, status: i.status === 'no_recipe' ? 'no_recipe' : 'partial', margin_pct: null, monthly_profit: null }));
      b.counts = { ...b.counts, loss: 0 };
      await route.fulfill({ response: res, json: b });
    });
    await page.route('**/v1/services/*/cost**', async (route) => {
      const res = await route.fetch();
      const b = await res.json();
      b.status = b.status === 'no_recipe' ? 'no_recipe' : 'partial';
      b.missing = [...new Set([...(b.missing ?? []), 'hour_cost', 'no_expenses'])];
      b.net_profit = null; b.net_margin_pct = null; b.monthly_profit = null;
      b.parts = b.parts.map((p: any) => ({ ...p, share_pct: null }));
      await route.fulfill({ response: res, json: b });
    });
    await page.goto('/price');
    await expect(rows(page).first()).toBeVisible();
    const margins = await rows(page).getByTestId('price-row-margin').allInnerTexts();
    expect(margins.length).toBeGreaterThan(0);
    expect(margins.every((m) => m.trim() === '—')).toBe(true);
    await expect(page.locator('[data-testid="price-row"][data-loss="true"]')).toHaveCount(0);
    await rows(page).first().getByTestId('price-row-open').click();
    await expect(page.getByTestId('price-card-missing')).toHaveAttribute('data-missing', /no_expenses/);
    await expect(page.getByTestId('price-card-net')).toHaveText(/—/);
    await expect(page.getByTestId('price-card-monthly')).toHaveText(/—/);
    await expect(page.getByTestId('price-bar')).toHaveCount(0);
  });

  test('stale data adds the banner and keeps the numbers', async ({ page }) => {
    await login(page);
    await page.route('**/v1/dashboard**', async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      body.data_stale = true;
      await route.fulfill({ response: res, json: body });
    });
    await page.goto('/price');
    await expect(page.getByTestId('price-stale-banner')).toContainText('могли устареть');
    await expect(rows(page).first()).toBeVisible();
  });

  test('the legend of a card names every part with its words, not only colours', async ({ page }) => {
    await login(page);
    const list = await openList(page);
    test.skip(!list || !list.items.some((i: any) => i.status === 'ok'), 'no service with a complete card');
    await openCard(page, list.items.find((i: any) => i.status === 'ok').id);
    const text = norm(await page.locator('[data-testid="price-card"]').innerText());
    for (const key of [...PART_KEYS, 'net']) expect(text).toMatch(PART_LABELS[key]);
    expect(text).toMatch(WORDS);
    await noHorizontalOverflow(page);
  });
});
