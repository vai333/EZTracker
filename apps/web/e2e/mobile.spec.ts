import { expect, test } from "@playwright/test";

for (const path of ["/today", "/board", "/review", "/courses", "/settings"]) {
  test(`no horizontal page scroll at 375px on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("board scrolls inside its own container on mobile", async ({ page }) => {
  await page.goto("/board");
  const strip = page.getByLabel("Board columns");
  await expect(strip).toBeVisible();
  const scrollable = await strip.evaluate((el) => el.scrollWidth > el.clientWidth);
  expect(scrollable).toBe(true);
});
