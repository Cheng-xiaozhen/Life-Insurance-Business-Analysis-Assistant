// With the Next dev server running: node scripts/check-scenario-navigation.mjs
import { chromium, expect } from "@playwright/test";

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const base = process.env.SCENARIOS_URL ?? "http://localhost:3000";
  await page.route("http://localhost:5518/**", (route) => route.fulfill({
    contentType: "application/json",
    body: route.request().url().endsWith("/info") ? "{}" : "[]",
  }));
  await page.route("**/api/scenarios", (route) => route.fulfill({
    contentType: "application/json", body: '{"scenarios":[]}',
  }));
  for (const threadId of [null, "12345678-1234-1234-1234-123456789012"]) {
    const params = new URLSearchParams({ apiUrl: "http://localhost:5518", assistantId: "agent", hideToolCalls: "true" });
    if (threadId) params.set("threadId", threadId);
    await page.goto(`${base}/?${params}`);
    await page.getByRole("link", { name: "分析场景管理" }).click();
    await expect(page).toHaveURL(`${base}/scenarios?${params}`);
    await page.reload();
    await page.getByRole("link", { name: "返回分析对话" }).click();
    await expect(page).toHaveURL(`${base}/?${params}`);
    await expect(page.getByLabel("Deployment URL", { exact: false })).toHaveCount(0);
  }
  await page.goto(`${base}/scenarios`);
  await expect(page.getByRole("link", { name: "返回分析对话" })).toHaveAttribute("href", "/");
  console.log("Scenario navigation: connection settings and thread survive round trip and reload.");
} finally {
  await browser.close();
}
