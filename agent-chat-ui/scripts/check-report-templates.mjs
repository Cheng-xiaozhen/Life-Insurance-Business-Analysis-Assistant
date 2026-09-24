// With Next dev running: node scripts/check-report-templates.mjs
import { chromium, expect } from "@playwright/test";
import { build } from "esbuild";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
const directory = await mkdtemp(path.join(tmpdir(), "report-check-"));
process.env.REPORT_TEMPLATE_DIR = directory;
const bundle = await build({
  entryPoints: ["src/app/api/report-templates/route.ts"],
  bundle: true,
  platform: "node",
  format: "esm",
  write: false,
});
const api = await import(
  `data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`
);
const sample = {
  code: "monthly_review_example",
  name: "月度经营分析报告（示例）",
  channel: "个险",
  period: "月度",
  target: "全系统",
  purpose: "检视经营",
  chapters: [
    {
      id: "c",
      name: "保费经营检视",
      text: "比较标保达成",
      metrics: ["标保"],
      mode: "对比",
      children: [],
    },
  ],
  tone: "客观",
  conclusion: "先结论",
  units: "万元",
  examples: [],
};
const post = (report, originalCode = null, headers = {}) =>
  api.POST(
    new Request("http://localhost:3000/api/report-templates", {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify({ report, originalCode }),
    }),
  );
expect((await api.GET()).status).toBe(200);
expect((await post(sample)).status).toBe(200);
for (const code of [
  "../escape",
  "CON",
  "a/b",
  "a.b",
  "a\\b",
  "MONTHLY_REVIEW_EXAMPLE",
])
  expect((await post({ ...sample, code })).status).toBe(400);
expect(
  (await post(sample, null, { origin: "https://example.com" })).status,
).toBe(403);
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  let failSave = false;
  await page.route("**/api/report-templates", async (route) => {
    const request = route.request();
    const response =
      request.method() === "GET"
        ? await api.GET()
        : failSave
          ? Response.json({ error: "模拟保存失败" }, { status: 500 })
          : await api.POST(
              new Request(request.url(), {
                method: "POST",
                headers: request.headers(),
                body: request.postData(),
              }),
            );
    await route.fulfill({
      status: response.status,
      contentType: "application/json",
      body: await response.text(),
    });
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto(
    `${process.env.SCENARIOS_URL ?? "http://localhost:3000"}/report-templates?assistantId=agent`,
  );
  await page.getByRole("button", { name: /月度经营分析报告/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByText("1. 保费经营检视", { exact: false }).first().click();
  await expect(page.getByLabel("分析步骤 *", { exact: true })).toBeHidden();
  await page.getByText("1. 保费经营检视", { exact: false }).first().click();
  await page.getByLabel("报告名称 *", { exact: true }).fill("未保存修改");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /月度经营分析报告/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新增报告模板", exact: true }).click();
  await page.getByRole("button", { name: "保存模板" }).click();
  await expect(page.getByRole("alert")).toContainText("请填写");
  await page
    .getByLabel("报告编码 *", { exact: true })
    .fill("monthly_review_example");
  await page.getByLabel("报告名称 *", { exact: true }).fill("测试报告");
  await page.getByLabel("板块名称 *", { exact: true }).fill("测试章节");
  await page
    .getByLabel("分析步骤 *", { exact: true })
    .first()
    .fill("分析总体情况");
  await page.getByLabel("关联指标", { exact: true }).fill("标保，价值，标保");
  await page.getByRole("button", { name: "添加子章节", exact: true }).click();
  await page.getByLabel("子章节板块名 *", { exact: true }).fill("测试子章节");
  await page
    .getByRole("group", { name: "步骤 1" })
    .getByLabel("分析步骤 *", { exact: true })
    .fill("第一项");
  await page.getByRole("button", { name: "添加步骤", exact: true }).click();
  await page
    .getByRole("group", { name: "步骤 2" })
    .getByLabel("分析步骤 *", { exact: true })
    .fill("第二项");
  await page.getByRole("button", { name: "上移步骤 2", exact: true }).click();
  await expect(
    page
      .getByRole("group", { name: "步骤 1" })
      .getByLabel("分析步骤 *", { exact: true }),
  ).toHaveValue("第二项");
  await page.getByRole("button", { name: "保存模板" }).click();
  await expect(page.getByRole("alert")).toContainText("报告编码已存在");
  await page.getByLabel("报告编码 *", { exact: true }).fill("test_report");
  await page
    .getByLabel("句式示例（每行一条）")
    .fill("句式一，包含逗号。\n句式二。");
  await page.getByRole("button", { name: "保存模板" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: /测试报告/ }).click();
  await expect(
    page
      .getByRole("group", { name: "步骤 1" })
      .getByLabel("分析步骤 *", { exact: true }),
  ).toHaveValue("第二项");
  await expect(
    page
      .getByRole("list", { name: "关联指标标签" })
      .first()
      .getByRole("listitem"),
  ).toHaveCount(2);
  await expect(page.getByLabel("句式示例（每行一条）")).toHaveValue(
    "句式一，包含逗号。\n句式二。",
  );
  await page.getByRole("button", { name: "删除步骤 1", exact: true }).click();
  await expect(
    page
      .getByRole("group", { name: "步骤 1" })
      .getByLabel("分析步骤 *", { exact: true }),
  ).toHaveValue("第一项");
  await page
    .getByRole("button", { name: "删除步骤 1", exact: true })
    .isDisabled()
    .then((value) => expect(value).toBe(true));
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const bounds = await page.getByRole("dialog").boundingBox();
  expect(bounds.width).toBe(390);
  await page.getByRole("button", { name: "保存模板" }).click();
  await expect(
    page.getByRole("link", { name: "返回分析对话" }),
  ).toHaveAttribute("href", "/?assistantId=agent");
  await page.getByRole("button", { name: /测试报告/ }).click();
  await page.getByLabel("报告编码 *", { exact: true }).fill("renamed_report");
  failSave = true;
  await page.getByRole("button", { name: "保存模板" }).click();
  await expect(page.getByRole("alert")).toContainText("模拟保存失败");
  await expect(page.getByLabel("报告编码 *", { exact: true })).toHaveValue(
    "renamed_report",
  );
  failSave = false;
  await page.getByRole("button", { name: "保存模板" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const files = await readdir(directory);
  expect(files).toContain("renamed_report.yaml");
  expect(files).not.toContain("test_report.yaml");
  const yaml = await readFile(
    path.join(directory, "renamed_report.yaml"),
    "utf8",
  );
  expect(yaml).toContain("报告编码: renamed_report");
  expect(yaml).toContain("步骤序号: 1");
  expect(yaml).toContain("写作风格与格式要求:");
  expect(yaml).not.toContain("id:");
  await page.reload();
  await page.getByRole("button", { name: /测试报告/ }).click();
  await expect(page.getByLabel("报告编码 *", { exact: true })).toHaveValue(
    "renamed_report",
  );
  expect(errors).toEqual([]);
  console.log(
    "Report templates: validation, cancel, collapse, tags, step ordering/deletion, persistence and mobile layout passed.",
  );
} finally {
  await browser.close();
  await rm(directory, { recursive: true, force: true });
}
