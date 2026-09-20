// Run: node scripts/check-execution-pane.mjs
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";

const result = await build({
  absWorkingDir: fileURLToPath(new URL("../", import.meta.url)),
  stdin: {
    contents: `import React from "react";
      import { createRoot } from "react-dom/client";
      import { ExecutionPane } from "./src/components/thread/execution-pane";
      const root = createRoot(document.getElementById("root"));
      window.show = (props) => root.render(React.createElement(ExecutionPane, props));`,
    resolveDir: fileURLToPath(new URL("../", import.meta.url)),
    loader: "tsx",
  },
  bundle: true,
  format: "iife",
  write: false,
});
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: result.outputFiles[0].text });
  const props = {
    running: true,
    status: "正在分析",
    entries: [
      {
        id: "match",
        analysis_id: "q1",
        label: "已识别场景：标保经营检视",
        state: "done",
      },
      {
        id: "fetch",
        analysis_id: "q1",
        label: "查询数据 · 步骤 1：标保情况",
        state: "done",
      },
      {
        id: "analyze",
        analysis_id: "q1",
        label: "生成步骤分析 · 步骤 1：标保情况",
        state: "running",
        message_id: "q1:step:1",
      },
    ],
    messages: [
      {
        id: "q1:step:1",
        type: "ai",
        content: "这是报告正文",
        additional_kwargs: { reasoning: "先核对指标，再分析趋势" },
      },
    ],
  };
  await page.evaluate((props) => window.show(props), props);
  const toggle = page.getByRole("button", { name: /思考过程/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("已识别场景：标保经营检视")).toBeVisible();
  await expect(page.getByText("这是报告正文")).toHaveCount(0);
  await page.getByText("模型思考", { exact: true }).click();
  await expect(page.getByText("先核对指标，再分析趋势")).toBeVisible();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("status")).toContainText("生成步骤分析");
  props.running = false;
  props.status = "已完成";
  props.entries[2].state = "done";
  await page.evaluate((props) => window.show(props), props);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("status")).toHaveText("已完成");
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("查询数据 · 步骤 1：标保情况")).toBeVisible();
  console.log(
    "Execution pane: live progress, reasoning, report separation, completion and keyboard toggle PASS",
  );
} finally {
  await browser.close();
}
