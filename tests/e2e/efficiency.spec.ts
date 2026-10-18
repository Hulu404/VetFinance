import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  SET06, WRITE, closeTip, email, fieldOf, forbiddenWords, login, noHorizontalOverflow, norm, openPage, openTip, password, q, rubText,
  ruPlural, toKopecks, toPct, url, val, withAnswer,
} from './stage5-helpers';

/**
 * Stage 5 e2e: "Эффективность клиники" (functions 33, 34).
 *
 * data-testid, texts and routes come from design/screens/efficiency.md (designer, 2026-10-18): /analytics/efficiency?month=YYYY-MM;
 * `as_of=YYYY-MM-DD` is passed to the API as is (not named in the spec; used for the golden clinic, see docs/handoff.md).
 * Two modes: rooms (`data-load-by="rooms"`) and doctors (the fallback, the main path at the start); the screen never shows a red colour or
 * a recommendation ("резерв роста", "простой" are forbidden words). The client never counts: hours, percents, hour cost and what an
 * hour brings come from the API.
 *
 * Generic part (any clinic): three cards, load rows and bars, hour cost with its lines, the month switcher, states (error, empty, hours not
 * set, no expenses), no overflow. Golden part (VF_E2E_SET06=1, clinic G, test-g@vetfinance.test): numbers equal expected.json (rooms mode).
 * Writing part (VF_E2E_WRITE=1, a clinic in the fallback mode): the dialog of hours is saved and restored.
 * Env: VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD.
 */
const expectedAll = JSON.parse(readFileSync(resolve(__dirname, '../golden/set06/expected.json'), 'utf-8'));
const GOLDEN_AS_OF: string = expectedAll.as_of;
const GOLDEN_MONTH: string = expectedAll.month;
const GE = expectedAll.cases.main.efficiency;
const AS_OF_Q = SET06 ? `as_of=${GOLDEN_AS_OF}` : '';

test.skip(!url || !email || !password, 'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD are not set');

const hoursText = (text: string): number[] => (norm(text).match(/\d+/g) ?? []).map(Number);

async function openEfficiency(page: Page, ...parts: string[]): Promise<any | null> {
  const api = await openPage(page, '/analytics/efficiency', '/v1/efficiency?', q(...parts, AS_OF_Q));
  await expect(page.getByTestId('efficiency')).toBeVisible();
  return api;
}

const figureValue = (x: any): number | null => val(x);
const loadRows = (page: Page) => page.getByTestId('efficiency-load-row');

// ================================================================== Generic
test.describe('Efficiency (stage 5, functions 33, 34)', () => {
  let page: Page;
  let api: any | null = null;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    api = await openEfficiency(page);
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test('the title, the subtitle and the month switcher with the status of the month', async () => {
    await expect(page.getByRole('heading', { level: 1, name: 'Эффективность клиники' })).toBeVisible();
    await expect(page.getByTestId('efficiency')).toContainText('Загрузка, стоимость часа и средний чек');
    await expect(page.getByTestId('efficiency-month')).toBeVisible();
    await expect(page.getByTestId('efficiency-period-status')).toContainText('месяц закрыт');
    // the last closed month is the last one: there is nothing after it
    await expect(page.getByTestId('efficiency-month-next')).toBeDisabled();
  });

  test('the mode is on the root and the cards equal the API: visits, load, average check', async () => {
    test.skip(!api, 'mock mode: no API response captured');
    await expect(page.getByTestId('efficiency')).toHaveAttribute('data-load-by', api.load_by);
    await expect(page.getByTestId('efficiency-visits')).toContainText(String(val(api.visits)));
    if (api.avg_check) expect(toKopecks(await page.getByTestId('efficiency-avg-check').innerText())).toBe(val(api.avg_check));
    if (api.load_pct) {
      expect(toPct(await page.getByTestId('efficiency-load').innerText())).toBe(val(api.load_pct));
      await expect(page.getByTestId('efficiency')).toContainText(api.load_by === 'rooms' ? 'по кабинетам' : 'по часам врачей');
    } else {
      await expect(page.getByTestId('efficiency-load')).toHaveText(/—/);
      await expect(page.getByTestId('efficiency')).toContainText('часы приёма не указаны');
    }
  });

  test('the headline is the API headline and does not judge ("много", "мало") or advise', async () => {
    test.skip(!api || !api.headline, 'no headline in the answer');
    const text = norm(await page.getByTestId('efficiency-headline').innerText());
    expect(text).toBe(norm(api.headline));
    expect(text).not.toMatch(/много|мало|рекоменду/i);
  });

  test('a row per room (rooms mode) or per doctor (fallback); each has a bar, the percent and the hours from the API', async () => {
    test.skip(!api, 'mock mode: no API response captured');
    const list = api.load_by === 'rooms' ? api.rooms : api.doctors;
    await expect(loadRows(page)).toHaveCount(list.length);
    for (let i = 0; i < list.length; i++) {
      const r = loadRows(page).nth(i);
      await expect(r).toHaveAttribute('data-id', list[i].id);
      await expect(r).toHaveAttribute('data-kind', api.load_by === 'rooms' ? 'room' : 'doctor');
      if (list[i].load_pct && val(list[i].load_pct) !== null) {
        const text = await r.getByTestId('efficiency-load-pct').innerText();
        expect(toPct(text), list[i].name).toBe(val(list[i].load_pct));
        const hours = hoursText(text.replace(/\d+(?:[,.]\d+)?\s*%/, ''));
        expect(hours).toContain(val(list[i].busy_hours));
        expect(hours).toContain(val(list[i].available_hours));
        await expect(r.getByTestId('efficiency-load-bar')).toHaveAttribute('role', 'img');
        expect((await r.getByTestId('efficiency-load-bar').getAttribute('aria-label')) ?? '').toMatch(/Загрузка/);
      } else {
        await expect(r.getByTestId('efficiency-no-hours')).toContainText('часы приёма не указаны');
      }
    }
    if (api.load_by === 'doctors') {
      await expect(page.getByTestId('efficiency-fallback-note')).toContainText('Расписания кабинетов нет, поэтому считаем по часам приёма врачей');
      await expect(page.getByTestId('efficiency')).toContainText('Загрузка по врачам');
    } else {
      await expect(page.getByTestId('efficiency-fallback-note')).toHaveCount(0);
      await expect(page.getByTestId('efficiency')).toContainText('Загрузка по кабинетам');
    }
  });

  test('the hour cost, what an hour brings and the table lines equal the API; the two lines of the cost add up to it', async () => {
    test.skip(!api || !api.hour_cost, 'no hour cost for this clinic');
    expect(toKopecks(await page.getByTestId('efficiency-hour-cost').innerText())).toBe(val(api.hour_cost));
    expect(api.hour_cost.breakdown.reduce((s: number, b: any) => s + b.value, 0)).toBe(val(api.hour_cost));
    if (api.hour_margin) expect(toKopecks(await page.getByTestId('efficiency-hour-margin').innerText())).toBe(val(api.hour_margin));
    for (const p of api.hour_cost_parts) {
      const line = page.locator(`[data-testid="efficiency-part"][data-key="${p.key}"]`);
      await expect(line).toHaveCount(1);
      const shown = await line.innerText();
      if (p.key === 'hours' || p.key === 'busy_hours') expect(hoursText(shown)).toContain(val(p.figure));
      else expect(toKopecks(shown)).toBe(val(p.figure));
    }
    await expect(page.getByTestId('efficiency')).toContainText('после лекарств, процентов врачам и комиссий');
  });

  test('numbers open tooltips with a breakdown: load, hour cost, average check', async () => {
    test.skip(!api || !api.load_pct, 'load is not computed for this clinic');
    for (const id of ['efficiency-load', 'efficiency-hour-cost', 'efficiency-avg-check']) {
      const tip = await openTip(page, page.getByTestId(id));
      await expect(tip).not.toBeEmpty();
      await closeTip(page);
    }
    const tip = await openTip(page, page.getByTestId('efficiency-load'));
    await expect(tip).toContainText(/Занято/);
    await expect(tip).toContainText(/Доступно/);
    await closeTip(page);
  });

  test('no forbidden words (reserves, idle time, roles, branches); no horizontal page overflow', async () => {
    expect(await forbiddenWords(page)).toEqual([]);
    await noHorizontalOverflow(page);
  });
});

// ================================================================== Golden
test.describe('Efficiency of the golden clinic G (set06, rooms mode)', () => {
  test.skip(!SET06, 'VF_E2E_SET06=1 is needed (clinic G seeded from tests/golden/set06)');

  test(`September ${GOLDEN_MONTH}: visits 254, load 21,2%, average check 1 981,50 ₽, hour cost 461,45 ₽, an hour brings 1 707,53 ₽`, async ({ page }) => {
    await login(page);
    await openEfficiency(page, `month=${GOLDEN_MONTH}`);
    await expect(page.getByTestId('efficiency')).toHaveAttribute('data-load-by', 'rooms');
    await expect(page.getByTestId('efficiency-visits')).toContainText(String(GE.visits));
    expect(toPct(await page.getByTestId('efficiency-load').innerText())).toBe(GE.load_pct);
    expect(toKopecks(await page.getByTestId('efficiency-avg-check').innerText())).toBe(GE.avg_check);
    expect(toKopecks(await page.getByTestId('efficiency-hour-cost').innerText())).toBe(GE.hour_cost);
    expect(toKopecks(await page.getByTestId('efficiency-hour-margin').innerText())).toBe(GE.hour_margin);
    const headline = norm(await page.getByTestId('efficiency-headline').innerText());
    expect(headline).toContain('21,2%');
    expect(headline).toContain(`свободно ${GE.free_hours} ${ruPlural(GE.free_hours, 'час', 'часа', 'часов')}`);
    expect(headline).toMatch(rubText(GE.hour_cost));
  });

  test('three rooms with their load and hours from expected.json; the fallback note is absent', async ({ page }) => {
    await login(page);
    await openEfficiency(page, `month=${GOLDEN_MONTH}`);
    await expect(loadRows(page)).toHaveCount(3);
    for (const room of GE.rooms as any[]) {
      const r = page.locator(`[data-testid="efficiency-load-row"][data-id="${room.id}"]`);
      await expect(r).toContainText(room.name);
      const text = await r.getByTestId('efficiency-load-pct').innerText();
      expect(toPct(text), room.name).toBe(room.load_pct);
      const hours = hoursText(text.replace(/\d+(?:[,.]\d+)?\s*%/, ''));
      expect(hours).toEqual(expect.arrayContaining([room.busy_hours, room.available_hours, room.free_hours]));
    }
    await expect(page.getByTestId('efficiency-fallback-note')).toHaveCount(0);
  });

  test('the table: 690 working hours (the operating room 137,5 h counted as 138), 146 busy; fixed 285 000 ₽ and obligations 33 400 ₽', async ({ page }) => {
    await login(page);
    await openEfficiency(page, `month=${GOLDEN_MONTH}`);
    const part = (key: string) => page.locator(`[data-testid="efficiency-part"][data-key="${key}"]`);
    expect(hoursText(await part('hours').innerText())).toContain(GE.available_hours);
    expect(hoursText(await part('busy_hours').innerText())).toContain(GE.busy_hours);
    expect(toKopecks(await part('fixed').innerText())).toBe(GE.pool.fixed);
    expect(toKopecks(await part('obligations').innerText())).toBe(GE.pool.obligations);
    const tip = await openTip(page, page.getByTestId('efficiency-hour-cost'));
    await expect(tip).toContainText(rubText(GE.hour_cost_lines.fixed));
    await expect(tip).toContainText(rubText(GE.hour_cost_lines.obligations));
    await closeTip(page);
  });

  test('a month after the last closed one is replaced by the last closed one, not shown as empty', async ({ page }) => {
    await login(page);
    await openEfficiency(page, 'month=2999-01');
    await expect(page.getByTestId('efficiency')).toBeVisible();
    await expect(page.getByTestId('efficiency-error')).toHaveCount(0);
    await expect(page.getByTestId('efficiency-month-next')).toBeDisabled();
  });
});

// ================================================================== Writing
test.describe('Writing: the hours of reception (the fallback mode)', () => {
  test.skip(!WRITE, 'VF_E2E_WRITE=1 is needed: the tests change data of the test clinic and restore it');
  test.describe.configure({ mode: 'serial' });

  test('the dialog refuses a wrong average duration, saves a new one and the screen is read again; the old value is restored', async ({ page }) => {
    await login(page);
    const api = await openEfficiency(page);
    test.skip(!api || api.load_by !== 'doctors', 'the hours dialog exists in the fallback mode only');
    await page.getByTestId('efficiency-hours-open').click();
    await expect(page.getByTestId('efficiency-hours-dialog')).toBeVisible();
    const minutes = await fieldOf(page, 'efficiency-hours-field-minutes');
    const before = await minutes.inputValue();
    try {
      await minutes.fill('4');
      await page.getByTestId('efficiency-hours-save').click();
      await expect(page.getByTestId('efficiency-hours-field-minutes-error')).toContainText('От 5 до 240 минут');
      await minutes.fill('241');
      await page.getByTestId('efficiency-hours-save').click();
      await expect(page.getByTestId('efficiency-hours-field-minutes-error')).toContainText('От 5 до 240 минут');
      const next = String(Number(before) === 45 ? 40 : 45);
      await minutes.fill(next);
      const saved = page.waitForResponse((r) => r.url().includes('/v1/efficiency/settings') && r.request().method() === 'PUT');
      const reread = page.waitForResponse((r) => r.url().includes('/v1/efficiency?') && r.request().method() === 'GET');
      await page.getByTestId('efficiency-hours-save').click();
      expect((await saved).status()).toBe(200);
      await reread;
      await expect(page.getByText('Часы приёма сохранены')).toBeVisible();
      const after = await (await reread).json();
      const doctorsBusy = (rows: any[]) => rows.map((d) => val(d.busy_hours));
      if (api.doctors.every((d: any) => d.busy_hours)) expect(doctorsBusy(after.doctors)).not.toEqual(doctorsBusy(api.doctors));
    } finally {
      // restore whatever the earlier state was; a failure here must be visible in the report, not hidden
      await page.goto('/analytics/efficiency');
      await page.getByTestId('efficiency-hours-open').click();
      await (await fieldOf(page, 'efficiency-hours-field-minutes')).fill(before);
      await page.getByTestId('efficiency-hours-save').click();
      await expect(page.getByText('Часы приёма сохранены')).toBeVisible();
    }
  });

  test('a doctor without hours: the field is validated and a value out of range is refused', async ({ page }) => {
    await login(page);
    const api = await openEfficiency(page);
    test.skip(!api || api.load_by !== 'doctors' || !api.doctors.length, 'the hours dialog exists in the fallback mode only');
    await page.getByTestId('efficiency-hours-open').click();
    const field = await fieldOf(page, `efficiency-hours-field-doctor-${api.doctors[0].id}`);
    const before = await field.inputValue();
    await field.fill('81');
    await page.getByTestId('efficiency-hours-save').click();
    await expect(page.getByTestId(`efficiency-hours-field-doctor-${api.doctors[0].id}-error`)).toContainText('От 0 до 80 часов');
    await field.fill('7.25');
    await page.getByTestId('efficiency-hours-save').click();
    await expect(page.getByTestId(`efficiency-hours-field-doctor-${api.doctors[0].id}-error`)).toContainText('Не больше одного знака после запятой');
    await field.fill(before);                       // nothing was sent: the dialog is closed without saving
    await page.keyboard.press('Escape');
  });
});

// ================================================================== States
test.describe('Efficiency states', () => {
  test('a server error shows the error card with Retry and keeps the month switcher', async ({ page }) => {
    await login(page);
    await page.route('**/v1/efficiency?**', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":{"code":"sync_failed","message":"x","details":{}}}' }));
    await page.goto('/analytics/efficiency');
    await expect(page.getByTestId('efficiency-error')).toContainText('Не получилось загрузить данные');
    await expect(page.getByTestId('efficiency-month')).toBeVisible();
    await page.unroute('**/v1/efficiency?**');
    await page.getByTestId('efficiency-error-retry').click();
    await expect(page.getByTestId('efficiency-error')).toHaveCount(0);
  });

  test('a month without visits shows the empty state and no cards', async ({ page }) => {
    await login(page);
    await withAnswer(page, '**/v1/efficiency?**', '/analytics/efficiency', (b) => {
      b.status = 'empty'; b.visits.value = 0; b.avg_check = null; b.load_pct = null; b.hour_cost = null; b.rooms = []; b.doctors = [];
      b.hour_cost_parts = [];
    });
    await expect(page.getByTestId('efficiency-empty')).toContainText('данных нет');
    await expect(page.getByTestId('efficiency-empty')).toContainText('Загрузите продажи из Ветменеджера');
    await expect(page.getByTestId('efficiency-load')).toHaveCount(0);
  });

  test('hours of reception not set: the banner with the action, dashes instead of load and hour cost, visits and check stay', async ({ page }) => {
    await login(page);
    await withAnswer(page, '**/v1/efficiency?**', '/analytics/efficiency', (b) => {
      b.status = 'partial'; b.partial_reasons = ['no_doctor_hours']; b.load_by = 'doctors'; b.rooms = [];
      b.load_pct = null; b.hour_cost = null; b.hour_margin = null; b.hour_cost_parts = [];
      b.doctors = (b.doctors ?? []).map((d: any) => ({ ...d, load_pct: null, available_hours: null, busy_hours: null, free_hours: null }));
    });
    const banner = page.getByTestId('efficiency-hours-banner');
    await expect(banner).toContainText('Загрузку и стоимость часа посчитать нельзя: не указаны часы приёма врачей.');
    await expect(banner.getByRole('button', { name: 'Указать часы приёма' })).toBeVisible();
    await expect(page.getByTestId('efficiency-load')).toHaveText(/—/);
    await expect(page.getByTestId('efficiency-hour-cost')).toHaveText(/—/);
    await expect(page.getByTestId('efficiency-visits')).not.toHaveText(/—/);
    await expect(page.getByTestId('efficiency')).toContainText('часы приёма не указаны');
    expect(await forbiddenWords(page)).toEqual([]);
  });

  test('a month without a bank statement: the banner, the load stays, the hour cost and what an hour brings are dashes', async ({ page }) => {
    await login(page);
    await withAnswer(page, '**/v1/efficiency?**', '/analytics/efficiency', (b) => {
      b.status = 'partial'; b.partial_reasons = ['no_expenses']; b.hour_cost = null; b.hour_margin = null; b.hour_cost_parts = [];
    });
    await expect(page.getByTestId('efficiency-expenses-banner')).toContainText('стоимость часа посчитать нельзя');
    await expect(page.getByTestId('efficiency-expenses-banner')).toContainText('Загрузите выписку');
    await expect(page.getByTestId('efficiency-hour-cost')).toHaveText(/—/);
    await expect(page.getByTestId('efficiency-hour-margin')).toHaveText(/—/);
    await expect(page.getByTestId('efficiency-load')).not.toHaveText(/—/);
  });

  test('stale data adds the banner and keeps the numbers', async ({ page }) => {
    await login(page);
    await page.route('**/v1/dashboard**', async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      body.data_stale = true;
      await route.fulfill({ response: res, json: body });
    });
    await page.goto('/analytics/efficiency');
    await expect(page.getByTestId('efficiency-stale-banner')).toContainText('могли устареть');
    await expect(page.getByTestId('efficiency-visits')).toBeVisible();
  });
});
