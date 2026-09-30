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
    if (url.pathname.endsWith("/runs/stream")) {
      const body = route.request().postDataJSON();
      runs.push(body);
      const human = body.input.messages.at(-1);
      const markdown = "# 月度经营报告\n\n## 标保概况\n\n模拟标保分析结论。";
      const values = {
        messages: [
          human,
          {
            type: "ai",
            id: `${human.id}:report`,
            content: markdown,
            additional_kwargs: {
              analysis: true,
              analysis_id: human.id,
              report: {
                title: "月度经营报告",
                markdown,
                sections: [
                  {
                    section_id: "1",
                    markdown: "## 标保概况\n\n模拟标保分析结论。",
                    charts: [
                      {
                        recommended: true,
                        chart_type: "bar",
                        step_id: 1,
                        dataset_id: "step:1:table:1",
                        dimensions: ["机构"],
                        metrics: ["达成率"],
                        description: "机构达成率对比",
                        reason: "有可比较数据",
                        units: { 达成率: "%" },
                        precision: { 达成率: 1 },
                        data: [
                          { 机构: "甲", 达成率: 80 },
                          { 机构: "乙", 达成率: 60 },
                        ],
                      },
                    ],
                  },
                ],
              },
            },
          },
          {
            type: "ai",
            id: `${human.id}:charts`,
            content: "图表已按章节收录于报告。",
            additional_kwargs: { analysis: true, analysis_id: human.id },
          },
        ],
        analysis_id: human.id,
        status: "已完成",
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: metadata\ndata: {"run_id":"test-run"}\n\nevent: values\ndata: ${JSON.stringify(values)}\n\nevent: end\ndata: null\n\n`,
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: url.pathname.endsWith("/info")
        ? "{}"
        : url.pathname.endsWith("/threads") &&
            route.request().method() === "POST"
          ? JSON.stringify({ thread_id: "test-thread" })
          : "[]",
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
  await expect.poll(() => runs.length).toBe(1);
  expect(runs[0].input.report_template_id).toBe("monthly");
  await expect(
    page.getByRole("heading", { name: "标保概况", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "下载报告", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("figure", { name: "步骤 1 图表" })).toBeVisible();
  await page.getByText("查看图表数据", { exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "80.0", exact: true }),
  ).toBeVisible();
  await expect(input).toHaveValue("");
  await input.fill("分析2026年8月个险经营情况");
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
    "Report picker: names only, selection/change/clear, report submission, section rendering/download, retry/empty and mobile passed.",
  );
} finally {
  await browser.close();
}
