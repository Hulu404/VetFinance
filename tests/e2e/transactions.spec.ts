import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Stage 1 e2e (golden set02): upload a statement -> assign a category with "remember rule" -> see it in the list;
 * resolve a duplicate; re-upload does not double anything.
 *
 * Needs a CLEAN clinic seeded from tests/golden/set02/initial.json (accounts with numbers, categories, starter rules)
 * and VF_E2E_SET02=1. The scenario writes data and is not repeatable on the same clinic: reset the clinic before a rerun.
 * Selectors (data-testid) are the tester's proposal, see docs/handoff.md (2026-10-11 tester -> frontend-developer).
 */
const url = process.env.VF_WEB_URL;
const email = process.env.VF_E2E_EMAIL;
const password = process.env.VF_E2E_PASSWORD;
const SET02 = resolve(__dirname, '../golden/set02');
const expected = JSON.parse(readFileSync(resolve(SET02, 'expected.json'), 'utf-8'));
const surnames: string[] = expected.pii.pii_surnames;

test.skip(
  !url || !email || !password || process.env.VF_E2E_SET02 !== '1',
  'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD and VF_E2E_SET02=1 (clean clinic seeded from set02) are required',
);

async function login(page: Page) {
  await page.goto('/');
  await page.getByLabel(/почт|e-?mail/i).fill(email!);
  await page.getByLabel(/парол/i).fill(password!);
  await page.getByRole('button', { name: /войти|вход/i }).click();
  await expect(page.getByTestId('balance-total')).toBeVisible();
}

async function openTransactions(page: Page) {
  // On 390/820 px the menu may be collapsed: the link is looked up by role, the test does not depend on layout.
  await page.getByRole('link', { name: /^транзакции$/i }).first().click();
  await expect(page.getByTestId('tx-list')).toBeVisible();
}

async function openTab(page: Page, name: RegExp) {
  await page.getByRole('tab', { name }).click();
}

async function uploadStatement(page: Page, file: string) {
  await page.getByTestId('import-open').click();
  await page.getByTestId('import-file').setInputFiles(resolve(SET02, file));
  await page.getByTestId('import-submit').click();
  await expect(page.getByTestId('import-result')).toBeVisible();
}

async function counter(page: Page, name: 'loaded' | 'already-loaded' | 'duplicates' | 'to-check'): Promise<number> {
  const text = await page.getByTestId(`import-${name}`).innerText();
  return Number(text.replace(/\D/g, ''));
}

async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test.describe.serial('Transactions: statement import, rules, duplicates', () => {
  let page: Page;

  test.beforeAll(async ({ browser }, info) => {
    const ctx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined, baseURL: url });
    page = await ctx.newPage();
    await login(page);
    await openTransactions(page);
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test('upload the first statement: counters match the golden expectation', async () => {
    const exp = expected.steps.import_file1;
    await uploadStatement(page, 'bank_statement_1.txt');
    expect(await counter(page, 'loaded')).toBe(exp.created);
    expect(await counter(page, 'duplicates')).toBe(exp.duplicates);
    expect(await counter(page, 'to-check')).toBe(exp.check);
    await page.getByTestId('import-close').click();
    await noHorizontalOverflow(page);
  });

  test('"На проверку" lists unclear operations; a category with a rule moves the row out', async () => {
    await openTab(page, /на проверку/i);
    const rows = page.getByTestId('tx-row');
    await expect(rows).toHaveCount(expected.steps.import_file1.check);
    // d29 ("4500", same supplier) is categorised by hand first, without a rule: the later rule must not touch it
    const manual = rows.filter({ hasText: '4500' });
    await manual.getByTestId('tx-category').click();
    await page.getByTestId('category-picker').getByRole('option', { name: 'Прочие расходы' }).click();
    await page.getByTestId('create-rule').uncheck();
    await page.getByTestId('category-save').click();
    await expect(rows).toHaveCount(expected.steps.import_file1.check - 1);
    const row = rows.filter({ hasText: '4471' }); // d07: "Оплата по счету 4471", supplier Vet-Snab
    await expect(row).toHaveCount(1);
    await row.getByTestId('tx-category').click();
    await page.getByTestId('category-picker').getByRole('option', { name: 'Препараты' }).click();
    await page.getByTestId('create-rule').check(); // label "Запомнить правило для этого контрагента"
    await page.getByTestId('category-save').click();
    // d07 and d28 (retroactive, same supplier, was without category) leave the tab; d29 was already out
    await expect(rows).toHaveCount(expected.steps.import_file1.check - 3);
    await openTab(page, /^все$/i);
    const retro = page.getByTestId('tx-row').filter({ hasText: '4490' });
    await expect(retro.getByTestId('tx-category')).toHaveText(/препараты/i);
    await expect(page.getByTestId('tx-row').filter({ hasText: '4500' }).getByTestId('tx-category')).toHaveText(/прочие расходы/i);
    const all = page.getByTestId('tx-row').filter({ hasText: '4471' });
    await expect(all.getByTestId('tx-category')).toHaveText(/препараты/i);
    await expect(all.getByTestId('tx-status')).not.toContainText(/проверк/i);
  });

  test('re-uploading the same file creates nothing', async () => {
    const before = await page.getByTestId('tx-row').count();
    await uploadStatement(page, 'bank_statement_1.txt');
    expect(await counter(page, 'loaded')).toBe(0);
    expect(await counter(page, 'already-loaded')).toBeGreaterThanOrEqual(expected.steps.reimport_file1.skipped_existing + expected.steps.reimport_file1.skipped_in_file);
    await page.getByTestId('import-close').click();
    await expect(page.getByTestId('tx-row')).toHaveCount(before);
  });

  test('the second statement: the new rule is applied to the new operations', async () => {
    const exp = expected.steps.import_file2;
    await uploadStatement(page, 'bank_statement_2.txt');
    expect(await counter(page, 'loaded')).toBe(exp.created);
    await page.getByTestId('import-close').click();
    await openTab(page, /^все$/i);
    for (const text of ['4519', '12/Б']) {
      // e2, e3: same supplier INN, the rule applies
      const r = page.getByTestId('tx-row').filter({ hasText: text });
      await expect(r.getByTestId('tx-category')).toHaveText(/препараты/i);
    }
    const other = page.getByTestId('tx-row').filter({ hasText: 'по счету 88' }); // e4: another supplier, no rule
    await expect(other.getByTestId('tx-status')).toContainText(/проверк/i);
  });

  test('"Дубли": pairs are shown; choosing which row to keep keeps the pair count', async () => {
    await openTab(page, /дубл/i);
    const pairs = page.getByTestId('dup-pair');
    const n = expected.duplicate_pairs.length - 1; // m_post is not entered in this scenario
    await expect(pairs).toHaveCount(n);
    const first = pairs.first();
    expect(await first.getByTestId('tx-row').count()).toBe(2);
    await first.getByTestId('keep-this').last().click();
    await expect(pairs).toHaveCount(n);
    expect(await pairs.first().getByTestId('tx-row').count()).toBe(2);
  });

  test('no false duplicates among the three equal payments of 18 September', async () => {
    await openTab(page, /^все$/i);
    const equal = page.getByTestId('tx-row').filter({ hasText: /8\s?500,00/ }).filter({ hasText: /18\.09|18 сент/i });
    expect(await equal.count()).toBe(3);
    await expect(equal.getByTestId('tx-status').filter({ hasText: /дубл/i })).toHaveCount(0);
  });

  test('the month summary is shown and the page holds no owner names', async () => {
    const income = await page.getByTestId('summary-income').innerText();
    expect(income).toMatch(/₽/);
    const html = (await page.content()).toLowerCase();
    for (const s of surnames) expect(html).not.toContain(s.toLowerCase());
    await noHorizontalOverflow(page);
  });

  test('a wrong-format file is rejected with a readable message and nothing is loaded', async () => {
    const before = await page.getByTestId('tx-row').count();
    await page.getByTestId('import-open').click();
    await page.getByTestId('import-file').setInputFiles(resolve(SET02, expected.bad_format.file));
    await page.getByTestId('import-submit').click();
    await expect(page.getByTestId('import-error')).toContainText(/1С/);
    await page.getByTestId('import-close').click();
    await expect(page.getByTestId('tx-row')).toHaveCount(before);
  });
});
