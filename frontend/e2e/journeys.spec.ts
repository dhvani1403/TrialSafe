import { expect, test, type Page } from "@playwright/test";

const PROFILE = {
  conditions: ["breast cancer"],
  age: 52,
  sex: "female",
  location: { lat: 39.9526, lon: -75.1652, label: "Philadelphia, Pennsylvania" },
  max_distance_mi: 60,
  ecog: 1,
  metastatic: true,
  comorbidities: [],
  treatments: ["chemotherapy"],
  medications: [],
};

async function withProfile(page: Page) {
  await page.addInitScript((p) => sessionStorage.setItem("trialmatch.profile.v1", JSON.stringify(p)), PROFILE);
}

test("home explains the product and shows live data", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("fine print");
  await expect(page.getByText(/open studies at/)).toBeVisible();
  await expect(page.getByText("not medical advice", { exact: false }).first()).toBeVisible();
});

test("wizard collects a profile and lands on results", async ({ page }) => {
  await page.goto("/match");
  const box = page.getByRole("combobox", { name: "Condition" });
  await box.fill("asthma");
  await box.press("Enter");
  await expect(page.getByRole("list", { name: "Your conditions" })).toContainText("asthma");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("radio", { name: "Female" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click(); // no location
  await page.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByRole("heading", { name: "Does this look right?" })).toBeVisible();
  await page.getByRole("button", { name: "Show my matches" }).click();
  await expect(page).toHaveURL(/\/results/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("open stud", { timeout: 20_000 });
});

test("free-text description fills the form", async ({ page }) => {
  await page.goto("/match");
  await page.getByRole("button", { name: /describe your situation/i }).click();
  await page.getByLabel("Describe your situation").fill("I'm a 62 year old woman with type 2 diabetes. I don't smoke.");
  await page.getByRole("button", { name: "Fill in the form" }).click();
  await expect(page.getByRole("status")).toContainText("age");
  await expect(page.getByRole("list", { name: "Your conditions" })).toContainText(/diabetes/i);
});

test("results are ranked, filterable and link to an annotated trial", async ({ page }) => {
  await withProfile(page);
  await page.goto("/results");
  const rows = page.locator("li[id^=r-]");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  const scores = await page.locator("li[id^=r-] svg + span").allInnerTexts();
  const nums = scores.map((s) => parseFloat(s));
  expect(nums).toEqual([...nums].sort((a, b) => b - a));

  await rows.first().getByRole("link").click();
  await expect(page.getByRole("heading", { name: /How you compare/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "You need to" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Needs attention" }).click();
});

test("saved studies build a printable summary", async ({ page }) => {
  await withProfile(page);
  await page.goto("/results");
  const first = page.locator("li[id^=r-]").first();
  await expect(first).toBeVisible({ timeout: 20_000 });
  await first.getByRole("button", { name: /^Save / }).click();
  await page.getByRole("link", { name: /Saved/ }).click();
  await expect(page.getByRole("heading", { name: "Studies to discuss with my doctor" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Print or save as PDF/ })).toBeVisible();
  await expect(page.getByText("To check with the study team").or(page.getByText("Nearest site")).first()).toBeVisible();
});

test("insights shows every evaluation", async ({ page }) => {
  await page.goto("/insights");
  for (const h of ["Reading eligibility rules", "Who gets fewer options", "The data behind it"]) {
    await expect(page.getByRole("heading", { name: h })).toBeVisible();
  }
});

test("annotation tool loads drafted gold lines", async ({ page }) => {
  await page.goto("/annotate");
  await expect(page.getByRole("heading", { name: "Gold standard review" })).toBeVisible();
  await expect(page.getByText(/of \d+ verified/)).toBeVisible();
});

test("results fit a phone screen @mobile", async ({ page }) => {
  await withProfile(page);
  await page.goto("/results");
  await expect(page.locator("li[id^=r-]").first()).toBeVisible({ timeout: 20_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
