import { expect, test } from '@playwright/test';

const url = process.env.VF_WEB_URL;
const email = process.env.VF_E2E_EMAIL;
const password = process.env.VF_E2E_PASSWORD;
// Optional: expected total in kopecks when the DB is seeded with tests/golden/set01 (clinic A, as_of 2026-09-09).
const expectedTotal = process.env.VF_EXPECT_TOTAL_KOPECKS;

test.skip(!url || !email || !password, 'VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD are not set');

// Parses "2 282 658,55 ₽" (nbsp / thin spaces, comma decimals) into kopecks.
function toKopecks(text: string): number {
  const m = text.replace(/[  \s]/g, '').match(/(-?\d+)(?:[,.](\d{1,2}))?/);
  if (!m) throw new Error(`no number in "${text}"`);
  const rub = Number(m[1]);
  const kop = Number((m[2] ?? '0').padEnd(2, '0'));
  return rub * 100 + (rub < 0 || m[1].startsWith('-') ? -kop : kop);
}

test('login -> Dashboard -> balance card shows a number, tooltip shows per-account breakdown', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel(/e-?mail|почт/i).fill(email!);
  await page.getByLabel(/парол/i).fill(password!);
  await page.getByRole('button', { name: /войти|вход/i }).click();

  // Dashboard is the landing page after login.
  await expect(page).toHaveURL(/dashboard|desk|\/$|рабочий/i);
  const card = page.getByTestId('balance-total');
  await expect(card).toBeVisible();
  const text = await card.innerText();
  expect(text).toMatch(/\d/);
  expect(text).toMatch(/₽|руб/);

  if (expectedTotal) {
    expect(toKopecks(text)).toBe(Number(expectedTotal));
  }

  // The tooltip opens by hover on desktop and by tap on mobile.
  const trigger = card.getByTestId('figure-tip-trigger');
  await trigger.hover().catch(() => undefined);
  if (!(await page.getByTestId('figure-tip').isVisible())) await trigger.click();
  const tip = page.getByTestId('figure-tip');
  await expect(tip).toBeVisible();
  const tipText = await tip.innerText();
  // At least two account lines (bank + cash) with amounts.
  expect((tipText.match(/₽/g) ?? []).length).toBeGreaterThanOrEqual(2);
  expect(tipText).toMatch(/Касса/i);
  expect(tipText).toMatch(/Расчётн/i);

  // No horizontal overflow at this viewport.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
