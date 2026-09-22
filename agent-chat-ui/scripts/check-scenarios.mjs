// With the Next dev server running: node scripts/check-scenarios.mjs
import { chromium, expect } from "@playwright/test";
import { build } from "esbuild";
import { mkdtemp, readdir, copyFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

// Exercise the real API and Python YAML store in an isolated directory.
const directory = await mkdtemp(path.join(tmpdir(), "scenario-check-"));
process.env.SCENARIO_TEMPLATE_DIR = directory;
const source = path.resolve("../config/templates/Scenario");
for (const file of await readdir(source)) {
  if (file.endsWith(".yaml"))
    await copyFile(path.join(source, file), path.join(directory, file));
}
const result = await build({
  entryPoints: ["src/app/api/scenarios/route.ts"],
  bundle: true,
  platform: "node",
  format: "esm",
  write: false,
});
const api = await import(
  `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`
);

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  let failLoad = false;
  let failSave = false;
  await page.route("**/api/scenarios", async (route) => {
    const request = route.request();
    const response =
      failLoad || (failSave && request.method() === "POST")
        ? Response.json({ error: "模拟文件服务不可用" }, { status: 500 })
        : request.method() === "GET"
          ? await api.GET()
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
  const load = async () => {
    await page.goto(
      `${process.env.SCENARIOS_URL ?? "http://localhost:3000"}/scenarios`,
    );
  };
  await load();
  await page.getByRole("button", { name: "标保经营检视", exact: true }).click();
  await expect(page.getByRole("group", { name: /^步骤/ })).toHaveCount(5);
  await expect(
    page.getByRole("list", { name: "触发关键词标签" }).getByRole("listitem"),
  ).toHaveCount(7);
  await page.getByRole("textbox", { name: "场景名称" }).fill("未保存的修改");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "标保经营检视", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新增场景", exact: true }).click();
  await page
    .getByRole("textbox", { name: "场景编码" })
    .fill("standard_premium_review");
  await page.getByRole("textbox", { name: "场景名称" }).fill("自定义场景");
  await page
    .getByRole("textbox", { name: "触发关键词" })
    .fill("测试， 经营，测试");
  await page
    .getByRole("button", { name: "添加触发关键词", exact: true })
    .click();
  await expect(
    page.getByRole("list", { name: "触发关键词标签" }).getByRole("listitem"),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "删除触发关键词：经营", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "触发关键词", exact: true })
    .fill("经营");
  await page
    .getByRole("textbox", { name: "触发关键词", exact: true })
    .press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("textbox", { name: "分析步骤", exact: true })
    .fill("第一步");
  await page
    .getByRole("textbox", { name: "关联指标" })
    .fill("指标甲，指标乙，指标甲");
  await page
    .getByRole("textbox", { name: "关联指标", exact: true })
    .press("Enter");
  await expect(
    page.getByRole("list", { name: "关联指标标签" }).getByRole("listitem"),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "删除关联指标：指标乙", exact: true })
    .click();
  // Saving also includes a value that has not yet been added with Enter.
  await page
    .getByRole("textbox", { name: "关联指标", exact: true })
    .fill("指标乙");
  await page
    .getByRole("textbox", { name: "分析模式（可选）" })
    .fill("自由分析模式");
  await page.getByRole("button", { name: "保存场景" }).click();
  await expect(page.getByRole("alert")).toContainText("场景编码已存在");
  await page.getByRole("textbox", { name: "场景编码" }).fill("custom_review");
  await page.getByRole("button", { name: "添加步骤" }).click();
  await page
    .getByRole("textbox", { name: "分析步骤", exact: true })
    .nth(1)
    .fill("第二步");
  await page.getByRole("button", { name: "上移步骤 2", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "分析步骤", exact: true }).first(),
  ).toHaveValue("第二步");
  await page.getByRole("button", { name: "保存场景" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const stored = (await (await api.GET()).json()).scenarios;
  const created = stored.find((s) => s.code === "custom_review");
  expect(created.steps.map((s) => s.text)).toEqual(["第二步", "第一步"]);
  expect(created.steps[1].metrics).toEqual(["指标甲", "指标乙"]);
  expect(created.keywords).toEqual(["测试", "经营"]);
  await load();
  await page.getByRole("button", { name: "自定义场景", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "分析模式（可选）" }).nth(1),
  ).toHaveValue("自由分析模式");
  await page.getByRole("button", { name: "删除步骤 1", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "删除步骤 1", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("textbox", { name: "分析步骤", exact: true }),
  ).toHaveValue("第一步");
  await page.getByRole("textbox", { name: "场景名称" }).fill("修改后的场景");
  await page.getByRole("button", { name: "保存场景" }).click();
  await expect(
    page.getByRole("button", { name: "修改后的场景", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "修改后的场景", exact: true }).click();
  await page.getByRole("textbox", { name: "场景编码" }).fill("renamed_review");
  failSave = true;
  await page.getByRole("button", { name: "保存场景" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "模拟文件服务不可用" }),
  ).toContainText("模拟文件服务不可用");
  await expect(page.getByRole("dialog")).toBeVisible();
  failSave = false;
  await page.getByRole("button", { name: "保存场景" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await readdir(directory)).toEqual(
    expect.arrayContaining(["renamed_review.yaml"]),
  );
  expect(await readdir(directory)).not.toContain("custom_review.yaml");
  const yaml = await readFile(
    path.join(directory, "renamed_review.yaml"),
    "utf8",
  );
  expect(yaml).toContain("场景编码: renamed_review");
  expect(yaml).toContain("步骤序号: 1");
  expect(yaml).toContain("指标甲");
  const post = (
    scenario,
    originalCode = null,
    origin = "http://localhost:3000",
  ) =>
    api.POST(
      new Request("http://localhost:3000/api/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json", origin },
        body: JSON.stringify({ scenario, originalCode }),
      }),
    );
  for (const code of ["../escape", "CON", "a/b", "a\\b"]) {
    expect((await post({ ...created, code })).status).toBe(400);
  }
  expect((await post(created, null, "https://other.test")).status).toBe(403);
  const original = stored.find((s) => s.code === "standard_premium_review");
  expect((await post(original, original.code)).status).toBe(200);
  expect(
    await readFile(path.join(directory, `${original.code}.yaml`), "utf8"),
  ).toContain("输入参数:");
  failLoad = true;
  await load();
  await expect(
    page.getByRole("alert").filter({ hasText: "模拟文件服务不可用" }),
  ).toContainText("模拟文件服务不可用");
  failLoad = false;
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "标保经营检视", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  console.log(
    "Scenario checks passed: editing, cancel, validation, lists, ordering, persistence, recovery.",
  );
} finally {
  await browser.close();
  await rm(directory, { recursive: true, force: true });
}
