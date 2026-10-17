import { expect, test, type Locator, type Page, type Response } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Stage 4 e2e: "Платёжный календарь" and "Обязательства" (functions 21, 22, 23, 43).
 *
 * data-testid and routes come from design/screens/calendar.md and obligations.md (designer, 2026-10-17, after the owner's decisions):
 * /planning/calendar?view=month|list&date=YYYY-MM-DD&as_of=YYYY-MM-DD, /planning/obligations?as_of=; as_of is passed to the API as is.
 * The window is 22 days, the first day is `as_of` (marked `data-today="true"` in the grid; there is no separate start point).
 * Red days: data-status="below_safe|below_zero" and the words "ниже запаса" (not only the colour).
 * The calendar has no "move" button: the scenario "gap -> suggestion -> gap closed" checks the suggestion on the screen
 * (`calendar-alert-suggestion[data-closes-gap]`) and recomputes the window from the API response with the move (the test
 * recomputes, the client never does). `alert.text` has no suggestion; the client appends `suggestion.text` in its own span.
 * A deferral of a counterparty is edited from the day breakdown (`calendar-deferral-*`); an obligation is CLOSED, not deleted
 * (`obligations-delete` = "Закрыть обязательство" in the edit dialog, `obligations-delete-confirm` = "Закрыть").
 *
 * Generic part (any clinic): 22 days, screen = API, red days, today marker, day breakdown and "balance after" each payment,
 * deferral buttons, tooltips, summary cards, alert card with the suggestion span and "Почему?", states, obligations cards and rows,
 * the form's field errors, no horizontal overflow at 1280 / 820 / 390.
 * Golden part (VF_E2E_SET05=1, clinic F seeded from tests/golden/set05, user test-f@vetfinance.test): numbers equal expected.json.
 * Writing part (VF_E2E_WRITE=1, a throw-away test clinic): create and close obligations, add and delete a manual payment, change a
 * deferral and the safe balance (all restored by the test; closed obligations stay in the list by design).
 * Env: VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD.
 */
const url = process.env.VF_WEB_URL;
const email = process.env.VF_E2E_EMAIL;
const password = process.env.VF_E2E_PASSWORD;
const SET05 = process.env.VF_E2E_SET05 === '1';
const WRITE = process.env.VF_E2E_WRITE === '1';
const expectedAll = JSON.parse(readFileSync(resolve(__dirname, '../golden/set05/expected.json'), 'utf-8'));
const GOLDEN_AS_OF: string = expectedAll.as_of; // 2026-10-07
const G = expectedAll.calendar.main;
const GH = expectedAll.calendar.high_safe;
const GO = expectedAll.obligations;
const WEEKDAYS = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const AS_OF_Q = SET05 ? `as_of=${GOLDEN_AS_OF}` : '';
const RED = ['below_safe', 'below_zero'];
const NO_GAP = 'Перенос одного платежа разрыв не закрывает. Если поставщик согласен подождать, укажите отсрочку у его платежа.';

test.skip(!url || !email || !password, 'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD are not set');

// ---------------------------------------------------------------- helpers
/** "−1 234 567,89 ₽" (nbsp, thin spaces, U+2212) -> kopecks (absolute value). */
function toKopecks(text: string): number {
  const clean = text.replace(/[\s   ]/g, '').replace(/−/g, '-');
  const m = clean.match(/(\d+)(?:[,.](\d{1,2}))?/);
  if (!m) throw new Error(`no number in "${text}"`);
  return Number(m[1]) * 100 + Number((m[2] ?? '0').padEnd(2, '0'));
}

/** The amount as it may be printed: "108 500 ₽", "76 663,82 ₽" (any spaces). */
function rubText(kopecks: number): RegExp {
  const r = Math.floor(Math.abs(kopecks) / 100);
  const k = Math.abs(kopecks) % 100;
  const body = String(r).replace(/\B(?=(\d{3})+(?!\d))/g, '[\\s\\u00a0\\u202f]?') + (k ? `,${String(k).padStart(2, '0')}` : '(,00)?');
  return new RegExp(body);
}

const norm = (s: string): string => s.replace(/[\s   ]+/g, ' ').trim();
const val = (fig: any): number => (fig && typeof fig === 'object' ? fig.value : fig);
const q = (...parts: string[]) => parts.filter(Boolean).join('&');
const isRed = (d: any) => d.status !== 'ok';
const monthOf = (iso: string) => iso.slice(0, 7);

function prevMonth(month: string): string {
  const [y, m] = month.split('-').map(Number);
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`;
}

async function login(page: Page) {
  await page.goto('/');
  await page.getByLabel(/почт|e-?mail/i).fill(email!);
  await page.getByLabel(/парол/i).fill(password!);
  await page.getByRole('button', { name: /войти|вход/i }).click();
  await expect(page.getByTestId('balance-total')).toBeVisible();
}

/** Opens a page and returns the JSON of the first matching GET response (null in mock mode). */
async function openPage(page: Page, path: string, apiPart: string, query: string): Promise<any | null> {
  const wait = page
    .waitForResponse((r: Response) => r.url().includes(apiPart) && r.request().method() === 'GET' && r.status() === 200, { timeout: 8000 })
    .then((r) => r.json())
    .catch(() => null);
  await page.goto(`${path}${query ? `?${query}` : ''}`);
  return wait;
}

async function openTip(page: Page, trigger: Locator) {
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

async function forbiddenWords(page: Page): Promise<string[]> {
  const text = (await page.locator('main').innerText()).toLowerCase();
  return [/\bии\b/, /нейросет/, /только просмотр/, /филиал/, /\bроль\b/, /\bбот\b/, /катастроф/].filter((re) => re.test(text)).map(String);
}

const row = (page: Page, date: string) => page.locator(`[data-testid="calendar-row"][data-date="${date}"]`);
const breakdown = (page: Page, date: string) => page.locator(`[data-testid="calendar-day"][data-date="${date}"]`);

/** Opens the list view with the given day selected (its breakdown is shown in calendar-day). */
async function openDay(page: Page, date: string) {
  await page.goto(`/planning/calendar?${q('view=list', `date=${date}`, AS_OF_Q)}`);
  await expect(breakdown(page, date)).toBeVisible();
  return breakdown(page, date);
}

/** Field of a form: the testid marks the input or its wrapper. */
async function fieldOf(page: Page, testId: string): Promise<Locator> {
  const el = page.getByTestId(testId);
  const input = el.locator('input, select, textarea');
  return (await input.count()) ? input.first() : el;
}
const field = (page: Page, name: string) => fieldOf(page, `obligations-field-${name}`);
const payField = (page: Page, name: string) => fieldOf(page, `calendar-payment-field-${name}`);

/** Closings after moving one payment, recomputed by the test from the API days (the client never does this). */
function recomputeWithMove(days: any[], move: { from: string; to: string; amount: number }): Map<string, number> {
  const out = new Map<string, number>();
  let bal = val(days[0].opening);
  for (const d of days) {
    let pays = d.payments.reduce((s: number, p: any) => s + val(p.amount), 0);
    if (d.date === move.from) pays -= move.amount;
    if (d.date === move.to) pays += move.amount;
    bal += val(d.income_forecast) - pays;
    out.set(d.date, bal);
  }
  return out;
}

/** {name, amount, from, to} of the flat suggestion of the contract. */
function moveOf(s: any) {
  return { name: s.payment_name, from: s.from_date, to: s.to_date, amount: val(s.amount) };
}

/** The alert card equals the API alert: title, text without the suggestion, the suggestion in its own span with data-closes-gap. */
async function expectAlertCard(card: Locator, a: any) {
  await expect(card).toHaveAttribute('data-date', a.date);
  await expect(card).toHaveAttribute('data-severity', a.severity);
  expect(norm(await card.getByTestId('calendar-alert-title').innerText())).toBe(norm(a.title));
  const text = card.getByTestId('calendar-alert-text');
  const shown = norm(await text.innerText());
  expect(shown).toContain(norm(a.text));
  const suggestion = text.getByTestId('calendar-alert-suggestion');
  if (a.suggestion) {
    await expect(suggestion).toHaveCount(1);
    expect(norm(await suggestion.innerText())).toBe(norm(a.suggestion.text));
    await expect(suggestion).toHaveAttribute('data-closes-gap', String(a.suggestion.closes_gap));
    expect(shown).toBe(norm(`${a.text} ${a.suggestion.text}`));
  } else {
    await expect(suggestion).toHaveCount(0);
    expect(shown).toContain(norm(NO_GAP));
  }
}

/** First payment of the API window that has a counterparty (a regular payment): [day, payment, index in the day]. */
function firstRegular(api: any): [any, any, number] | null {
  for (const d of api.days) {
    const i = d.payments.findIndex((p: any) => p.counterparty);
    if (i >= 0) return [d, d.payments[i], i];
  }
  return null;
}

const deferralText = (days: number) => (days > 0 ? /отсрочка\s+\d+\s+(день|дня|дней)/ : /без отсрочки/);

// ================================================================== Calendar
test.describe('Payment calendar (stage 4, functions 21, 22, 43)', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    await expect(page.getByTestId('calendar')).toBeVisible();
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test('the list has 22 days in a row from as_of, each with its weekday; the subtitle names the window', async () => {
    const rows = page.getByTestId('calendar-row');
    await expect(rows).toHaveCount(22);
    const dates = (await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-date')))) as string[];
    const first = new Date(`${dates[0]}T00:00:00Z`);
    dates.forEach((d, i) => expect(d).toBe(new Date(first.getTime() + i * 86400000).toISOString().slice(0, 10)));
    if (api) {
      expect(dates).toEqual(api.days.map((d: any) => d.date));
      expect([api.window.from, api.window.to]).toEqual([dates[0], dates[21]]);
      expect(dates[0]).toBe(api.as_of);
      const sub = await page.getByTestId('calendar-subtitle').innerText();
      expect(sub).toContain(String(Number(dates[0].slice(8))));
      expect(sub).toContain(String(Number(dates[21].slice(8))));
    }
    for (const d of dates.slice(0, 7)) await expect(row(page, d)).toContainText(WEEKDAYS[(new Date(`${d}T00:00:00Z`).getUTCDay() + 6) % 7]);
  });

  test('the closing of every day equals the API; red days carry the status and the words "ниже запаса"', async () => {
    const rows = page.getByTestId('calendar-row');
    const n = await rows.count();
    for (let i = 0; i < n; i++) {
      const r = rows.nth(i);
      const status = (await r.getAttribute('data-status')) ?? '';
      if (api) {
        expect(toKopecks(await r.getByTestId('calendar-row-closing').innerText()), api.days[i].date).toBe(val(api.days[i].closing));
        expect(status).toBe(api.days[i].status);
      }
      if (RED.includes(status)) await expect(r).toContainText('ниже запаса');
      else await expect(r).not.toContainText('ниже запаса');
    }
  });

  test('the breakdown of a day: morning, every payment with the balance after it, income, evening, note', async () => {
    test.skip(!api, 'mock mode: no API response captured');
    const d = api.days.find((x: any) => x.payments.length > 1) ?? api.days.find((x: any) => x.payments.length) ?? api.days[0];
    const box = await openDay(page, d.date);
    await expect(box).toHaveAttribute('data-status', d.status);
    expect(toKopecks(await box.getByTestId('calendar-day-opening').innerText())).toBe(val(d.opening));
    expect(toKopecks(await box.getByTestId('calendar-day-income').innerText())).toBe(val(d.income_forecast));
    expect(toKopecks(await box.getByTestId('calendar-day-closing').innerText())).toBe(val(d.closing));
    expect(norm(await box.getByTestId('calendar-day-note').innerText())).toBe(norm(d.note));
    const pays = box.getByTestId('calendar-day-payment');
    await expect(pays).toHaveCount(d.payments.length);
    for (let i = 0; i < d.payments.length; i++) {
      const p = d.payments[i];
      await expect(pays.nth(i)).toHaveAttribute('data-source', p.source);
      await expect(pays.nth(i)).toHaveAttribute('data-payment-id', p.id);
      await expect(pays.nth(i)).toContainText(p.name);
      expect(toKopecks(await pays.nth(i).getByTestId('calendar-day-payment-amount').innerText())).toBe(val(p.amount));
      // "останется N" / "не хватит N": the number is shown without a sign
      expect(toKopecks(await pays.nth(i).getByTestId('calendar-day-payment-after').innerText())).toBe(Math.abs(val(p.balance_after)));
      const after = await pays.nth(i).getByTestId('calendar-day-payment-after').innerText();
      expect(/не хватит/.test(after)).toBe(val(p.balance_after) < 0);
    }
    const tip = await openTip(page, box.getByTestId('calendar-day-closing'));
    await expect(tip).toContainText('На утро');
    for (const p of d.payments) await expect(tip).toContainText(p.name);
    await closeTip(page);
  });

  test('a regular payment has the deferral button with the counterparty terms; other sources have none', async () => {
    test.skip(!api, 'mock mode: no API response captured');
    const found = firstRegular(api);
    test.skip(!found, 'no regular payment with a counterparty in this window');
    const d = found![0];
    const box = await openDay(page, d.date);
    const pays = box.getByTestId('calendar-day-payment');
    for (let i = 0; i < d.payments.length; i++) {
      const p = d.payments[i];
      const edit = pays.nth(i).getByTestId('calendar-deferral-edit');
      if (p.counterparty) {
        await expect(edit).toHaveCount(1);
        await expect(edit).toHaveAttribute('data-payment-id', p.id);
        await expect(edit).toHaveAttribute('data-days', String(p.max_deferral_days));
        await expect(edit).toHaveText(deferralText(p.max_deferral_days));
      } else {
        await expect(edit).toHaveCount(0);
      }
    }
  });

  test('the deferral dialog shows the field errors with the designer texts and saves nothing', async () => {
    test.skip(!api, 'mock mode: no API response captured');
    const found = firstRegular(api);
    test.skip(!found, 'no regular payment with a counterparty in this window');
    const [d, p, i] = found!;
    const box = await openDay(page, d.date);
    await box.getByTestId('calendar-day-payment').nth(i).getByTestId('calendar-deferral-edit').click();
    const dialog = page.getByTestId('calendar-deferral-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(p.counterparty.name);
    const input = dialog.getByTestId('calendar-deferral-input');
    await expect(input).toHaveValue(String(p.max_deferral_days));
    let patched = false;
    page.on('request', (r) => {
      if (r.url().includes('/v1/counterparties/') && r.method() === 'PATCH') patched = true;
    });
    for (const [typed, message] of [['abc', 'Только целое число дней'], ['31', 'От 0 до 30 дней'], ['', 'Укажите число дней, 0 — без отсрочки']] as const) {
      await input.fill(typed);
      await dialog.getByTestId('calendar-deferral-save').click();
      await expect(dialog.getByTestId('calendar-deferral-error')).toContainText(message);
    }
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`); // leaves the dialog without saving
    expect(patched, 'a value the screen cannot accept is never saved').toBe(false);
  });

  test('summary cards equal the API and open tooltips', async () => {
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
    for (const id of ['calendar-income', 'calendar-expense', 'calendar-lowest', 'calendar-safe']) await expect(page.getByTestId(id).first()).toBeVisible();
    if (api) {
      expect(toKopecks(await page.getByTestId('calendar-income').innerText())).toBe(val(api.summary.income));
      expect(toKopecks(await page.getByTestId('calendar-expense').innerText())).toBe(val(api.summary.expense));
      await expect(page.getByTestId('calendar-payments-count')).toContainText(String(api.summary.payments_count));
      expect(toKopecks(await page.getByTestId('calendar-lowest').innerText())).toBe(val(api.summary.lowest.balance));
      await expect(page.getByTestId('calendar-lowest')).toHaveAttribute('data-status', api.summary.lowest.status);
      await expect(page.getByTestId('calendar-lowest-date')).toContainText(String(new Date(`${api.summary.lowest.date}T00:00:00Z`).getUTCDate()));
      if (api.safe_balance_set) expect(toKopecks(await page.getByTestId('calendar-safe').first().innerText())).toBe(val(api.safe_balance));
      else await expect(page.getByTestId('calendar-safe').first()).toContainText('не задан');
    }
    for (const id of ['calendar-income', 'calendar-expense', 'calendar-lowest']) {
      const tip = await openTip(page, page.getByTestId(id));
      await expect(tip).not.toBeEmpty();
      await closeTip(page);
    }
  });

  test('every alert is a card with severity, title, text, the suggestion span and "Почему?" with steps', async () => {
    const cards = page.getByTestId('calendar-alert');
    if (api) await expect(cards).toHaveCount(Math.min(api.alerts.length, 3));
    const n = await cards.count();
    for (let i = 0; i < n; i++) {
      const card = cards.nth(i);
      if (api) await expectAlertCard(card, api.alerts[i]);
      await card.getByTestId('calendar-alert-why').click();
      await expect(card.getByTestId('calendar-alert-why-panel').or(page.getByTestId('calendar-alert-why-panel')).first()).toBeVisible();
    }
  });

  test('the month view marks the same red days, today is the first day of the window, the chart agrees', async () => {
    await page.goto(`/planning/calendar?${q('view=month', AS_OF_Q)}`);
    await expect(page.getByTestId('calendar-grid')).toBeVisible();
    const cells = page.getByTestId('calendar-cell');
    await expect(cells).toHaveCount(22);
    const redCells = await cells.evaluateAll((els) => els.filter((e) => ['below_safe', 'below_zero'].includes(e.getAttribute('data-status') ?? '')).map((e) => e.getAttribute('data-date')));
    if (api) expect(redCells).toEqual(api.days.filter(isRed).map((d: any) => d.date));
    for (const date of redCells) await expect(page.locator(`[data-testid="calendar-cell"][data-date="${date}"]`).getByTestId('calendar-cell-badge')).toHaveText(/ниже запаса/);
    const today = page.locator('[data-testid="calendar-cell"][data-today="true"]');
    await expect(today).toHaveCount(1);
    await expect(today).toHaveAttribute('data-date', await cells.first().getAttribute('data-date') as string);
    if (api) await expect(today).toHaveAttribute('data-date', api.as_of);
    await expect(page.getByTestId('calendar-today')).toHaveCount(0);
    const chart = page.getByTestId('calendar-chart');
    if (await chart.count()) {
      await expect(page.getByTestId('calendar-safe-line')).toBeVisible();
      const redPoints = await page.getByTestId('calendar-chart-point').evaluateAll((els) => els.filter((e) => ['below_safe', 'below_zero'].includes(e.getAttribute('data-status') ?? '')).map((e) => e.getAttribute('data-date')));
      expect(redPoints).toEqual(redCells);
      await expect(page.getByTestId('calendar-chart-point')).toHaveCount(22);
    }
  });

  test('the link under the grid leads to the safe balance in Settings', async () => {
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
    await page.getByTestId('calendar-safe-link').first().click();
    await expect(page).toHaveURL(/\/settings\/main/);
    await expect(page.getByTestId('settings-safe-balance')).toBeVisible();
  });

  test('the manual payment dialog: required fields are checked before anything is sent', async () => {
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
    let posted = false;
    page.on('request', (r) => {
      if (r.url().includes('/v1/calendar/payments') && r.method() === 'POST') posted = true;
    });
    await page.getByTestId('calendar-add-payment').first().click();
    await expect(page.getByTestId('calendar-payment-dialog')).toBeVisible();
    await page.getByTestId('calendar-payment-save').click();
    await expect(page.getByTestId('calendar-payment-field-name-error')).toContainText('Напишите, за что платёж');
    await expect(page.getByTestId('calendar-payment-field-amount-error')).toContainText('Укажите сумму');
    expect(posted).toBe(false);
    await (await payField(page, 'amount')).fill('0');
    await page.getByTestId('calendar-payment-save').click();
    await expect(page.getByTestId('calendar-payment-field-amount-error')).toContainText('Сумма должна быть больше нуля');
    await page.keyboard.press('Escape');
  });

  test('no forbidden words; no horizontal page overflow', async () => {
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
    await expect(page.getByTestId('calendar-row').first()).toBeVisible();
    expect(await forbiddenWords(page)).toEqual([]);
    await noHorizontalOverflow(page);
  });
});

// ================================================================== Gap -> suggestion -> gap closed (golden, clinic F)
test.describe('Gap, suggestion, gap closed (golden set05)', () => {
  test.skip(!SET05, 'VF_E2E_SET05=1 is needed (clinic F seeded from tests/golden/set05)');

  test('9-11 October are red; the alert suggests moving «Зоовет» to 12 October; with the move no day is red', async ({ page }) => {
    await login(page);
    const api = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    const redRows = await page.locator('[data-testid="calendar-row"]').evaluateAll((els) => els.filter((e) => ['below_safe', 'below_zero'].includes(e.getAttribute('data-status') ?? '')).map((e) => e.getAttribute('data-date')));
    expect(redRows).toEqual(G.days.filter((d: any) => d.below_safe).map((d: any) => d.date));
    for (const d of G.days) expect(toKopecks(await row(page, d.date).getByTestId('calendar-row-closing').innerText()), d.date).toBe(d.closing);

    const a = G.alerts[0];
    const card = page.getByTestId('calendar-alert');
    await expect(card).toHaveCount(1);
    await expect(card).toHaveAttribute('data-date', a.date);
    await expect(card).toHaveAttribute('data-severity', a.severity);
    await expect(card.getByTestId('calendar-alert-title')).toHaveText(rubText(a.shortfall));
    const text = card.getByTestId('calendar-alert-text');
    await expect(text).toContainText(rubText(a.lowest));
    const suggestion = text.getByTestId('calendar-alert-suggestion');
    await expect(suggestion).toHaveAttribute('data-closes-gap', 'true');
    await expect(suggestion).toContainText('Зоовет');
    await expect(suggestion).toContainText(rubText(a.suggestion.amount));
    await expect(suggestion).toContainText('12 октября');
    await expect(suggestion).toContainText('разрыва не будет');
    expect(norm(await text.innerText())).toBe(norm(a.text));

    // the gap is closed: the move from the API suggestion, applied by the test to the API days, leaves no red day
    test.skip(!api, 'mock mode: the response is needed for the recomputation');
    const alert = api.alerts[0];
    const move = moveOf(alert.suggestion);
    expect(move).toEqual({ name: a.suggestion.name, from: a.suggestion.from, to: a.suggestion.to, amount: a.suggestion.amount });
    expect(alert.suggestion.closes_gap).toBe(true);
    expect(alert.date_to).toBe(a.end_date);
    const after = recomputeWithMove(api.days, move);
    for (const x of a.after) expect(after.get(x.date), x.date).toBe(x.closing);
    expect([...after.values()].every((b) => b >= G.safe_balance)).toBe(true);
    await noHorizontalOverflow(page);
  });

  test('summary, today marker and the sources of payments of the golden clinic', async ({ page }) => {
    await login(page);
    await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    expect(toKopecks(await page.getByTestId('calendar-income').innerText())).toBe(G.summary.income);
    expect(toKopecks(await page.getByTestId('calendar-expense').innerText())).toBe(G.summary.expense);
    expect(toKopecks(await page.getByTestId('calendar-lowest').innerText())).toBe(G.summary.lowest.balance);
    await expect(page.getByTestId('calendar-payments-count')).toContainText(String(G.summary.payments_count));
    expect(toKopecks(await page.getByTestId('calendar-safe').first().innerText())).toBe(G.safe_balance);
    const oct8 = await openDay(page, '2026-10-08');
    await expect(oct8.getByTestId('calendar-day-payment').filter({ hasText: 'Кредит на аппарат УЗИ' })).toHaveAttribute('data-source', 'obligation');
    await expect(oct8.getByTestId('calendar-day-payment').filter({ hasText: 'Кредит на аппарат УЗИ' }).getByTestId('calendar-deferral-edit')).toHaveCount(0);
    await expect(oct8.getByTestId('calendar-day-payment').filter({ hasText: 'Чистый дом' }).getByTestId('calendar-deferral-edit')).toHaveAttribute('data-days', '3');
    const after = G.days[1].payments.map((p: any) => p.balance_after);
    const shown = await oct8.getByTestId('calendar-day-payment-after').allInnerTexts();
    expect(shown.map(toKopecks)).toEqual(after);
    const oct7 = await openDay(page, '2026-10-07');
    await expect(oct7.getByTestId('calendar-day-payment').filter({ hasText: 'Зоовет' }).getByTestId('calendar-deferral-edit')).toHaveAttribute('data-days', '5');
    const oct14 = await openDay(page, '2026-10-14');
    await expect(oct14.getByTestId('calendar-day-payment').filter({ hasText: 'Ремонт кондиционера' })).toHaveAttribute('data-source', 'manual');
    await expect(oct14.getByTestId('calendar-day-payment').filter({ hasText: 'Ремонт кондиционера' }).getByTestId('calendar-payment-delete')).toHaveCount(1);
    await page.goto(`/planning/calendar?${q('view=month', AS_OF_Q)}`);
    await expect(page.locator('[data-testid="calendar-cell"][data-today="true"]')).toHaveAttribute('data-date', GOLDEN_AS_OF);
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
    await expect(page.getByTestId('calendar')).not.toContainText('Ростелеком'); // October paid early, on the 2nd
  });

  test('the Dashboard shows the advice "cash_gap" with the calendar text and a link to the day', async ({ page }) => {
    await login(page);
    const dash = await openPage(page, '/', '/v1/dashboard', AS_OF_Q);
    const card = page.locator('[data-testid="advice-card"][data-advice-id="cash_gap"]');
    await expect(card).toHaveCount(1);
    const a = G.alerts[0];
    expect(norm(await card.innerText())).toContain(norm(a.title));
    expect(norm(await card.innerText())).toContain(norm(a.text));
    const link = card.getByTestId('advice-calendar-link');
    await expect(link).toHaveCount(1);
    if (dash) {
      const advice = dash.advice.find((x: any) => x.id === 'cash_gap');
      expect(advice.link).toEqual({ path: '/planning/calendar', date: a.date });
      expect(norm(advice.text)).toBe(norm(a.text));
    }
    await link.click();
    await expect(page).toHaveURL(new RegExp(`/planning/calendar.*date=${a.date}`));
  });
});

// ================================================================== Obligations
test.describe('Obligations (stage 4, function 23)', () => {
  test('cards and rows equal the API; every amount opens a tooltip; no overflow', async ({ page }) => {
    await login(page);
    const api = await openPage(page, '/planning/obligations', '/v1/obligations', AS_OF_Q);
    await expect(page.getByTestId('obligations')).toBeVisible();
    for (const id of ['obligations-debt', 'obligations-payment', 'obligations-amortization']) {
      const tip = await openTip(page, page.getByTestId(id));
      await expect(tip).not.toBeEmpty();
      await closeTip(page);
    }
    if (api) {
      expect(toKopecks(await page.getByTestId('obligations-debt').innerText())).toBe(val(api.debt_total));
      expect(toKopecks(await page.getByTestId('obligations-payment').innerText())).toBe(val(api.monthly_payment));
      expect(toKopecks(await page.getByTestId('obligations-amortization').innerText())).toBe(val(api.amortization_month));
      const pnl = page.getByTestId('obligations-pnl');
      await expect(pnl).toHaveAttribute('data-month', api.pnl_month.month);
      expect(toKopecks(await pnl.innerText())).toBe(val(api.pnl_month.amount));
      const loanRows = page.getByTestId('obligations-loan-row');
      await expect(loanRows).toHaveCount(api.loans.length);
      await expect(page.getByTestId('obligations-equipment-row')).toHaveCount(api.equipment.length);
      expect(await loanRows.evaluateAll((els) => els.map((e) => e.getAttribute('data-id')))).toEqual(api.loans.map((l: any) => l.id)); // active, paid, closed
      for (const l of api.loans) {
        const r = page.locator(`[data-testid="obligations-loan-row"][data-id="${l.id}"]`);
        await expect(r).toHaveAttribute('data-kind', l.kind);
        await expect(r).toHaveAttribute('data-status', l.status);
        if (l.status === 'active') {
          expect(toKopecks(await r.getByTestId('obligations-loan-remaining').innerText())).toBe(val(l.remaining));
          expect(toKopecks(await r.getByTestId('obligations-loan-payment').innerText())).toBe(val(l.payment));
          await expect(r.getByTestId('obligations-edit')).toHaveCount(1);
        } else {
          await expect(r.getByTestId('obligations-status-pill')).toHaveAttribute('data-status', l.status);
          if (l.status === 'closed') await expect(r.getByTestId('obligations-edit')).toHaveCount(0);
        }
      }
      for (const e of api.equipment) {
        const r = page.locator(`[data-testid="obligations-equipment-row"][data-id="${e.id}"]`);
        await expect(r).toHaveAttribute('data-status', e.status);
        if (e.status === 'active') expect(toKopecks(await r.getByTestId('obligations-equipment-monthly').innerText())).toBe(val(e.monthly));
        else await expect(r.getByTestId('obligations-status-pill')).toHaveAttribute('data-status', e.status);
      }
    }
    expect(await forbiddenWords(page)).toEqual([]);
    await noHorizontalOverflow(page);
  });

  test('golden: clinic F to the kopeck, the paid autoclave goes last, and the P&L row of the month is the same number', async ({ page }) => {
    test.skip(!SET05, 'VF_E2E_SET05=1 is needed');
    await login(page);
    await openPage(page, '/planning/obligations', '/v1/obligations', AS_OF_Q);
    expect(toKopecks(await page.getByTestId('obligations-debt').innerText())).toBe(GO.debt_total);
    expect(toKopecks(await page.getByTestId('obligations-payment').innerText())).toBe(GO.monthly_payment);
    expect(toKopecks(await page.getByTestId('obligations-amortization').innerText())).toBe(GO.amortization_month);
    const pnlLine = page.getByTestId('obligations-pnl');
    await expect(pnlLine).toHaveAttribute('data-month', '2026-10');
    expect(toKopecks(await pnlLine.innerText())).toBe(GO.charges_month.total);
    const autoclave = page.locator('[data-testid="obligations-equipment-row"]', { hasText: 'Автоклав' });
    await expect(autoclave).toHaveAttribute('data-status', 'paid');
    const equipmentRows = page.getByTestId('obligations-equipment-row');
    await expect(equipmentRows.last()).toContainText('Автоклав');
    await page.goto(`/reports/pnl?month=2026-10&as_of=${GOLDEN_AS_OF}`);
    expect(toKopecks(await page.locator('[data-testid="pnl-row-amount"][data-key="obligations"]').innerText())).toBe(expectedAll.pnl_obligations_row['2026-10']);
  });

  test('the form shows field errors and sends nothing when required fields are empty', async ({ page }) => {
    await login(page);
    await openPage(page, '/planning/obligations', '/v1/obligations', AS_OF_Q);
    let posted = false;
    page.on('request', (r) => {
      if (r.url().includes('/v1/obligations') && r.method() === 'POST') posted = true;
    });
    await page.getByTestId('obligations-add-equipment').click();
    await expect(page.getByTestId('obligations-dialog')).toBeVisible();
    await page.getByTestId('obligations-save').click();
    await expect(page.getByTestId('obligations-field-name-error')).toBeVisible();
    await expect(page.getByTestId('obligations-field-cost-error')).toBeVisible();
    expect(posted).toBe(false);
    await page.keyboard.press('Escape');
  });
});

// ================================================================== The forms change data (VF_E2E_WRITE=1)
test.describe('Writing: obligations are created and CLOSED, deferral, manual payment, safe balance', () => {
  test.skip(!WRITE, 'VF_E2E_WRITE=1 is needed: the tests change data of the test clinic and restore it');
  test.describe.configure({ mode: 'serial' });

  const obligationsPath = () => `/planning/obligations${AS_OF_Q ? `?${AS_OF_Q}` : ''}`;

  /** Closes an obligation through the edit dialog; the row stays in the list as "закрыт" (decision of the owner, 2026-10-16). */
  async function closeRow(page: Page, rowTestId: string, name: string) {
    await page.goto(obligationsPath());
    const r = page.locator(`[data-testid="${rowTestId}"]`, { hasText: name });
    await r.getByTestId('obligations-edit').click();
    await expect(page.getByTestId('obligations-dialog')).toBeVisible();
    await page.getByTestId('obligations-delete').click();
    await expect(page.getByText(/Прошлые месяцы отчёта не изменятся/)).toBeVisible();
    const closed = page.waitForResponse((res) => res.url().includes('/v1/obligations/') && res.request().method() === 'DELETE');
    await page.getByTestId('obligations-delete-confirm').click();
    expect((await closed).status()).toBe(204);
    await expect(page.getByText('Обязательство закрыто')).toBeVisible();
    const after = page.locator(`[data-testid="${rowTestId}"]`, { hasText: name });
    await expect(after).toHaveCount(1);
    await expect(after).toHaveAttribute('data-status', 'closed');
    await expect(after.getByTestId('obligations-status-pill')).toHaveAttribute('data-status', 'closed');
    await expect(after.getByTestId('obligations-edit')).toHaveCount(0);
  }

  test('new equipment adds its amortization to the obligations and to the P&L; closing it takes the current month away and keeps the past', async ({ page }) => {
    await login(page);
    const before = await openPage(page, '/planning/obligations', '/v1/obligations', AS_OF_Q);
    test.skip(!before, 'mock mode');
    const asOf: string = before.as_of ?? GOLDEN_AS_OF;
    const month = monthOf(asOf);
    const last = prevMonth(month);
    const inService = `${prevMonth(last)}-10`; // two months back: amortized in the previous month and in this one
    const name = `Стоматологическая установка e2e ${Date.now() % 100000}`;
    const pnlOf = async (m: string) => {
      await page.goto(`/reports/pnl?month=${m}&as_of=${asOf}`);
      return toKopecks(await page.locator('[data-testid="pnl-row-amount"][data-key="obligations"]').innerText());
    };
    const [curBefore, lastBefore] = [await pnlOf(month), await pnlOf(last)];

    await page.goto(obligationsPath());
    await page.getByTestId('obligations-add-equipment').click();
    await (await field(page, 'name')).fill(name);
    await (await field(page, 'cost')).fill('360000');
    await (await field(page, 'life_years')).fill('5');
    await (await field(page, 'in_service_from')).fill(inService);
    const posted = page.waitForResponse((r) => r.url().includes('/v1/obligations') && r.request().method() === 'POST');
    await page.getByTestId('obligations-save').click();
    expect((await posted).status()).toBe(201);
    const r = page.locator('[data-testid="obligations-equipment-row"]', { hasText: name });
    await expect(r).toHaveCount(1);
    await expect(r).toHaveAttribute('data-status', 'active');
    expect(toKopecks(await r.getByTestId('obligations-equipment-monthly').innerText())).toBe(600000); // 360 000 ₽ / 60 months
    expect(toKopecks(await page.getByTestId('obligations-amortization').innerText())).toBe(val(before.amortization_month) + 600000);
    expect(toKopecks(await page.getByTestId('obligations-pnl').innerText())).toBe(val(before.pnl_month.amount) + 600000);
    expect(await pnlOf(month)).toBe(curBefore + 600000);
    expect(await pnlOf(last)).toBe(lastBefore + 600000);

    await closeRow(page, 'obligations-equipment-row', name);
    expect(toKopecks(await page.getByTestId('obligations-amortization').innerText())).toBe(val(before.amortization_month));
    expect(await pnlOf(month)).toBe(curBefore);
    expect(await pnlOf(last), 'the accrual of the past month stays after closing').toBe(lastBefore + 600000);
  });

  test('a new loan shows its payment in the calendar on the payment day; after closing it is gone', async ({ page }) => {
    await login(page);
    const cal = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    test.skip(!cal, 'mock mode');
    const target = cal.days.slice(3).find((d: any) => !['сб', 'вс'].includes(d.weekday)).date as string;
    const name = `Кредит e2e ${Date.now() % 100000}`;
    await page.goto(obligationsPath());
    await page.getByTestId('obligations-add-loan').click();
    const kind = page.getByTestId('obligations-kind');
    if (await kind.count()) await kind.getByRole('radio', { name: /кредит/i }).click().catch(() => undefined);
    await (await field(page, 'name')).fill(name);
    await (await field(page, 'lender')).fill('Тест-банк');
    await (await field(page, 'principal')).fill('100000');
    await (await field(page, 'remaining')).fill('100000');
    await (await field(page, 'rate')).fill('12');
    await (await field(page, 'payment')).fill('9000');
    await (await field(page, 'payment_day')).fill(String(Number(target.slice(8))));
    await page.getByTestId('obligations-save').click();
    await expect(page.locator('[data-testid="obligations-loan-row"]', { hasText: name })).toHaveCount(1);

    const box = await openDay(page, target);
    const pay = box.getByTestId('calendar-day-payment').filter({ hasText: name });
    await expect(pay).toHaveCount(1);
    await expect(pay).toHaveAttribute('data-source', 'obligation');
    expect(toKopecks(await pay.getByTestId('calendar-day-payment-amount').innerText())).toBe(900000);

    await closeRow(page, 'obligations-loan-row', name);
    const again = await openDay(page, target);
    await expect(again.getByTestId('calendar-day-payment').filter({ hasText: name })).toHaveCount(0);
  });

  test('a deferral is saved from the day breakdown and the calendar is read again', async ({ page }) => {
    await login(page);
    const api = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    test.skip(!api, 'mock mode');
    const found = firstRegular(api);
    test.skip(!found, 'no regular payment with a counterparty in this window');
    const [d, p, i] = found!;
    const old: number = p.max_deferral_days;
    const next = old === 4 ? 6 : 4;

    async function setDeferral(value: number) {
      const box = await openDay(page, d.date);
      const edit = box.getByTestId('calendar-day-payment').nth(i).getByTestId('calendar-deferral-edit');
      await edit.click();
      const dialog = page.getByTestId('calendar-deferral-dialog');
      await dialog.getByTestId('calendar-deferral-input').fill(String(value));
      const patch = page.waitForResponse((r) => r.url().includes('/v1/counterparties/') && r.request().method() === 'PATCH');
      const reread = page.waitForResponse((r) => r.url().includes('/v1/calendar') && r.request().method() === 'GET' && r.status() === 200);
      await dialog.getByTestId('calendar-deferral-save').click();
      const res = await patch;
      expect(res.status()).toBe(200);
      expect(await res.json()).toEqual({ id: p.counterparty.id, name: p.counterparty.name, max_deferral_days: value });
      await reread;
      await expect(page.getByText('Отсрочка сохранена')).toBeVisible();
      await expect(dialog).toBeHidden();
      await expect(edit).toHaveAttribute('data-days', String(value));
    }
    try {
      await setDeferral(next);
    } finally {
      await setDeferral(old);
    }
  });

  test('a manual payment is added to the calendar and deleted; the evening balance follows', async ({ page }) => {
    await login(page);
    const api = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    test.skip(!api, 'mock mode');
    const day = api.days[10];
    const name = `Тест e2e ${Date.now() % 100000}`;
    await page.getByTestId('calendar-add-payment').first().click();
    await (await payField(page, 'name')).fill(name);
    await (await payField(page, 'amount')).fill('1500');
    await (await payField(page, 'date')).fill(day.date);
    const posted = page.waitForResponse((r) => r.url().includes('/v1/calendar/payments') && r.request().method() === 'POST');
    await page.getByTestId('calendar-payment-save').click();
    expect((await posted).status()).toBe(201);
    await expect(page.getByText('Платёж добавлен')).toBeVisible();
    const box = await openDay(page, day.date);
    const pay = box.getByTestId('calendar-day-payment').filter({ hasText: name });
    await expect(pay).toHaveCount(1);
    await expect(pay).toHaveAttribute('data-source', 'manual');
    expect(toKopecks(await pay.getByTestId('calendar-day-payment-amount').innerText())).toBe(150000);
    expect(toKopecks(await box.getByTestId('calendar-day-closing').innerText())).toBe(val(day.closing) - 150000);
    await expect(pay.getByTestId('calendar-deferral-edit')).toHaveCount(0);

    await pay.getByTestId('calendar-payment-delete').click();
    const deleted = page.waitForResponse((r) => r.url().includes('/v1/calendar/payments/') && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Удалить' }).last().click();
    expect((await deleted).status()).toBe(204);
    await expect(page.getByText('Платёж удалён')).toBeVisible();
    await expect(box.getByTestId('calendar-day-payment').filter({ hasText: name })).toHaveCount(0);
    expect(toKopecks(await box.getByTestId('calendar-day-closing').innerText())).toBe(val(day.closing));
  });

  test('a date outside the window is refused with the window in the message', async ({ page }) => {
    await login(page);
    const api = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    test.skip(!api, 'mock mode');
    const before = new Date(`${api.window.from}T00:00:00Z`);
    before.setUTCDate(before.getUTCDate() - 1);
    await page.getByTestId('calendar-add-payment').first().click();
    await (await payField(page, 'name')).fill('Вне окна e2e');
    await (await payField(page, 'amount')).fill('100');
    await (await payField(page, 'date')).fill(before.toISOString().slice(0, 10));
    await page.getByTestId('calendar-payment-save').click();
    await expect(page.getByTestId('calendar-payment-field-date-error')).toContainText('в окне календаря');
  });

  test('golden: the safe balance 250 000 ₽ from Settings makes the first suggestion partial; 150 000 ₽ brings the full one back', async ({ page }) => {
    test.skip(!SET05, 'VF_E2E_SET05=1 is needed');
    await login(page);
    const setSafe = async (rubles: string) => {
      await page.goto('/settings/main');
      await page.getByTestId('settings-safe-balance-input').fill(rubles);
      const patch = page.waitForResponse((r) => r.url().includes('/v1/clinic') && r.request().method() === 'PATCH');
      await page.getByTestId('settings-safe-balance-save').click();
      expect((await patch).status()).toBe(200);
      await expect(page.getByText('Запас сохранён')).toBeVisible();
    };
    try {
      await setSafe(String(GH.safe_balance / 100));
      const api = await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
      const redRows = await page.locator('[data-testid="calendar-row"]').evaluateAll((els) => els.filter((e) => ['below_safe', 'below_zero'].includes(e.getAttribute('data-status') ?? '')).map((e) => e.getAttribute('data-date')));
      expect(redRows).toEqual(GH.days.filter((d: any) => d.below_safe).map((d: any) => d.date));
      const cards = page.getByTestId('calendar-alert');
      await expect(cards).toHaveCount(GH.alerts.length);
      for (let i = 0; i < GH.alerts.length; i++) {
        const sug = cards.nth(i).getByTestId('calendar-alert-suggestion');
        await expect(sug).toHaveAttribute('data-closes-gap', String(GH.alerts[i].suggestion.closes_gap));
        expect(norm(await sug.innerText())).toBe(norm(GH.alerts[i].suggestion.text));
        if (api) await expectAlertCard(cards.nth(i), api.alerts[i]);
      }
      await expect(cards.first().getByTestId('calendar-alert-suggestion')).toContainText('уменьшит разрыв, но не закроет его');
    } finally {
      await setSafe(String(G.safe_balance / 100));
    }
    await openPage(page, '/planning/calendar', '/v1/calendar', q('view=list', AS_OF_Q));
    await expect(page.getByTestId('calendar-alert').first().getByTestId('calendar-alert-suggestion')).toHaveAttribute('data-closes-gap', 'true');
  });

  test('golden: a deferral of 0 days for «Зоовет» removes its suggestion; 5 days bring it back', async ({ page }) => {
    test.skip(!SET05, 'VF_E2E_SET05=1 is needed');
    await login(page);
    const setDeferral = async (value: number) => {
      const box = await openDay(page, '2026-10-07');
      await box.getByTestId('calendar-day-payment').filter({ hasText: 'Зоовет' }).getByTestId('calendar-deferral-edit').click();
      const dialog = page.getByTestId('calendar-deferral-dialog');
      await dialog.getByTestId('calendar-deferral-input').fill(String(value));
      await dialog.getByTestId('calendar-deferral-save').click();
      await expect(dialog).toBeHidden();
    };
    try {
      await setDeferral(0);
      await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
      const card = page.getByTestId('calendar-alert').first();
      await expect(card).toHaveAttribute('data-date', G.alerts[0].date);
      await expect(card.getByTestId('calendar-alert-text')).not.toContainText('Зоовет');
    } finally {
      await setDeferral(5);
    }
    await page.goto(`/planning/calendar?${q('view=list', AS_OF_Q)}`);
    await expect(page.getByTestId('calendar-alert').first().getByTestId('calendar-alert-suggestion')).toContainText('Зоовет');
  });
});

// ================================================================== States
test.describe('Calendar states', () => {
  test('a server error shows the error card with Retry', async ({ page }) => {
    await login(page);
    await page.route('**/v1/calendar**', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":{"code":"sync_failed","message":"x","details":{}}}' }));
    await page.goto('/planning/calendar?view=list');
    await expect(page.getByTestId('calendar-error')).toBeVisible();
    await page.unroute('**/v1/calendar**');
    await page.getByTestId('calendar-error-retry').click();
    await expect(page.getByTestId('calendar-row').first()).toBeVisible();
  });

  /** Opens the list with the answer of the API changed by `patch`. */
  async function withAnswer(page: Page, patch: (body: any) => void) {
    await page.route('**/v1/calendar**', async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      patch(body);
      await route.fulfill({ response: res, json: body });
    });
    await page.goto('/planning/calendar?view=list');
  }

  test('a calendar without red days shows no alert card and no "ниже запаса"', async ({ page }) => {
    await login(page);
    await withAnswer(page, (body) => {
      body.alerts = [];
      for (const d of body.days) d.status = 'ok';
      body.summary.lowest.status = 'ok';
    });
    await expect(page.getByTestId('calendar-row').first()).toBeVisible();
    await expect(page.getByTestId('calendar-alert')).toHaveCount(0);
    await expect(page.getByTestId('calendar')).not.toContainText('ниже запаса');
  });

  test('a short history shows the partial banner with its reason', async ({ page }) => {
    await login(page);
    await withAnswer(page, (body) => {
      body.status = 'partial';
      body.partial_reasons = ['short_history', 'obligations_missing'];
      body.history_days = 34;
    });
    const banner = page.getByTestId('calendar-partial-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('data-reasons', /short_history/);
    await expect(banner).toHaveAttribute('data-reasons', /obligations_missing/);
    await expect(page.getByTestId('calendar-row').first()).toBeVisible();
  });

  test('without statements the empty state offers to load one', async ({ page }) => {
    await login(page);
    await withAnswer(page, (body) => {
      body.status = 'empty';
      body.partial_reasons = [];
      body.history_days = 0;
      body.data_as_of = null;
    });
    await expect(page.getByTestId('calendar-empty')).toBeVisible();
    await expect(page.getByTestId('calendar-empty-action')).toBeVisible();
  });

  test('a safe balance that is not set says so and links to Settings', async ({ page }) => {
    await login(page);
    await withAnswer(page, (body) => {
      body.safe_balance_set = false;
      body.safe_balance.value = 0;
    });
    await expect(page.getByTestId('calendar-safe').first()).toContainText('не задан');
    await expect(page.getByTestId('calendar-safe-link').first()).toBeVisible();
  });
});

// ================================================================== Settings: safe balance
test.describe('Settings: safe balance', () => {
  test('the field shows the saved value and refuses what it cannot accept', async ({ page }) => {
    await login(page);
    const clinic = await openPage(page, '/settings/main', '/v1/clinic', '');
    const card = page.getByTestId('settings-safe-balance');
    await expect(card).toBeVisible();
    const input = page.getByTestId('settings-safe-balance-input');
    if (clinic) expect(toKopecks(await input.inputValue() || '0')).toBe(clinic.safe_balance);
    for (const [typed, message] of [['abc', 'Введите сумму цифрами'], ['-5', 'Запас не может быть меньше нуля']] as const) {
      await input.fill(typed);
      await page.getByTestId('settings-safe-balance-save').click();
      await expect(page.getByTestId('settings-safe-balance-error')).toContainText(message);
    }
    await noHorizontalOverflow(page);
  });
});
