import { expect, test, type Locator, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/board");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("region", { name: "Needs Review column" })).toBeVisible();
});

const col = (page: Page, name: string) => page.getByRole("region", { name: `${name} column` });
// cards are the outermost role=button containing the title (inner toggles mention it too, but come later in DOM order)
const card = (scope: Locator | Page, title: string) => scope.getByRole("button", { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }).first();

async function drag(page: Page, from: Locator, to: Locator) {
  const a = (await from.boundingBox())!;
  const b = (await to.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + 20);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 10, a.y + 30, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + 120, { steps: 12 });
  await page.mouse.up();
}

test("drag a card from Needs Review to a course → persists after reload", async ({ page }) => {
  const review = col(page, "Needs Review");
  const cms = col(page, "Crafting Marketing Strategies with Prof. Siddarth Menon");
  await drag(page, card(review, "Growth & GTM"), cms);
  await expect(page.getByText("Moved to CMS")).toBeVisible();
  await expect(card(cms, "Growth & GTM")).toBeVisible();
  await page.reload();
  await expect(card(col(page, "Crafting Marketing Strategies with Prof. Siddarth Menon"), "Growth & GTM")).toBeVisible();
  await expect(card(col(page, "Needs Review"), "Growth & GTM")).toHaveCount(0);
});

test("undo from the toast and with ⌘Z", async ({ page }) => {
  const review = col(page, "Needs Review");
  const cms = col(page, "Crafting Marketing Strategies with Prof. Siddarth Menon");
  await drag(page, card(review, "Growth & GTM"), cms);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(card(col(page, "Needs Review"), "Growth & GTM")).toBeVisible();

  await drag(page, card(col(page, "Needs Review"), "Growth & GTM"), cms);
  await expect(card(cms, "Growth & GTM")).toBeVisible();
  await expect(page.getByText("Moved to CMS")).toBeVisible(); // undo token has arrived
  await page.keyboard.press("ControlOrMeta+z");
  await expect(card(col(page, "Needs Review"), "Growth & GTM")).toBeVisible();
});

test("keyboard drag and drop: space, arrow right, space", async ({ page }) => {
  const target = card(col(page, "Needs Review"), "Growth & GTM");
  await target.focus();
  await page.keyboard.press("Space");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Space");
  await expect(page.getByText(/^Moved to /)).toBeVisible();
  await expect(card(col(page, "Needs Review"), "Growth & GTM")).toHaveCount(0);
});

test("Move to… menu files a card without dragging", async ({ page }) => {
  await card(col(page, "Needs Review"), "Start-up Leader").focus();
  await page.keyboard.press("m");
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder("Type a course…").fill("byob");
  await page.keyboard.press("Enter");
  await expect(card(col(page, "Build Your Own Business (BYOB)"), "Start-up Leader")).toBeVisible();
});

test("toggle submitted collapses the card into the Submitted accordion", async ({ page }) => {
  const dddm = col(page, "Data Driven Decision Making with Prof. Vinay Sharma");
  await dddm.getByRole("button", { name: 'Mark "Zepto Case Analysis" as submitted' }).click();
  await expect(dddm.getByRole("button", { name: /Submitted \(1\)/ })).toBeVisible();
  await page.reload();
  await expect(col(page, "Data Driven Decision Making with Prof. Vinay Sharma").getByRole("button", { name: /Submitted \(1\)/ })).toBeVisible();
});

test("theme toggle persists across reloads", async ({ page }) => {
  await page.getByRole("button", { name: /^Theme: system/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: /^Theme: light/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("item drawer shows instructions, Open in Nexus and history", async ({ page }) => {
  await page.goto("/today");
  await page.getByRole("button", { name: /^Important: END TERM ASSIGNMENT/ }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("Submit your end term deck")).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Open in Nexus" })).toHaveAttribute("href", /students\.mesaschool\.co\.in/);
  await expect(drawer.getByText("parsed from text — please confirm")).toBeVisible();
  await expect(drawer.getByText(/^First seen/).first()).toBeVisible();
});

test("command palette finds an item and opens it", async ({ page }) => {
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByPlaceholder("Search items, courses, actions…").fill("lenskart");
  await page.getByRole("option", { name: /Session 7 Lenskart Workbook/ }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Session 7 Lenskart Workbook" })).toBeVisible();
});
