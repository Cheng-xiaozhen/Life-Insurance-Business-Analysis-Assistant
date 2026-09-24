// With Next dev running: node scripts/check-report-template-picker.mjs
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  const runs = [];
  let mode = "success";
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("http://localhost:5518/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.includes("/runs"))
      runs.push(route.request().postDataJSON());
    await route.fulfill({
      contentType: "application/json",
      body: url.pathname.endsWith("/info") ? "{}" : "[]",
    });
  });
  await page.route("**/api/report-templates", (route) =>
    route.fulfill({
      status: mode === "error" ? 500 : 200,
      contentType: "application/json",
      body: JSON.stringify(
        mode === "error"
          ? { error: "读取模板失败" }
          : {
              reports:
                mode === "empty"
                  ? []
                  : [
                      { code: "monthly", name: "月度经营报告" },
                      { code: "annual", name: "年度经营报告" },
                    ],
            },
      ),
    }),
  );
  await page.goto(
    `${process.env.SCENARIOS_URL ?? "http://localhost:3000"}/?apiUrl=http%3A%2F%2Flocalhost%3A5518&assistantId=agent`,
  );
  const input = page.getByRole("textbox", { name: "分析问题或补充参数" });
  await input.fill("分析2026年8月个险经营情况");
  await page.getByRole("button", { name: "选择报告模板", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("dialog")).not.toContainText("monthly");
  await page.getByRole("button", { name: "月度经营报告", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(input).toHaveValue("分析2026年8月个险经营情况");
  await page.getByRole("button", { name: "生成报告", exact: true }).click();
  await expect(
    page.getByText("报告生成流程尚未接通，已保留所选模板和问题。", {
      exact: true,
    }),
  ).toBeVisible();
  await input.press("Enter");
  await expect(input).toHaveValue("分析2026年8月个险经营情况");
  expect(runs).toEqual([]);
  await page
    .getByRole("button", { name: "更换报告模板：月度经营报告" })
    .click();
  await page.getByRole("button", { name: "年度经营报告", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "更换报告模板：年度经营报告" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "取消报告模板选择，返回智能问答" })
    .click();
  await expect(
    page.getByRole("button", { name: "Send", exact: true }),
  ).toBeEnabled();
  await expect(input).toHaveValue("分析2026年8月个险经营情况");
  mode = "error";
  await page.getByRole("button", { name: "选择报告模板", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("读取模板失败");
  mode = "empty";
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(
    page.getByText("暂无报告模板，请先在报告模板管理页面新增。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭模板选择" }).click();
  mode = "success";
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "选择报告模板", exact: true }).click();
  const box = await page.getByRole("dialog").boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(errors).toEqual([]);
  console.log(
    "Report picker: names only, selection/change/clear, draft preservation, no analysis submission, retry/empty and mobile passed.",
  );
} finally {
  await browser.close();
}
