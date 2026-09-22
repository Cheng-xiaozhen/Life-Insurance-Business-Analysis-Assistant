// Run from agent-chat-ui: node scripts/check-analysis-charts.mjs
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";

const root = fileURLToPath(new URL("../", import.meta.url));
const result = await build({
  absWorkingDir: root,
  stdin: {
    contents: `import React from "react";
      import { createRoot } from "react-dom/client";
      import { AnalysisCharts } from "./src/components/thread/analysis-charts";
      const root = createRoot(document.getElementById("root"));
      window.show = (value) => root.render(React.createElement(AnalysisCharts, {value}));`,
    resolveDir: root,
    loader: "tsx",
  },
  bundle: true,
  format: "iife",
  write: false,
});
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setContent(
    '<style>.h-72 {height:288px}</style><div id="root" style="width:800px"></div>',
  );
  await page.addScriptTag({ content: result.outputFiles[0].text });
  const chart = {
    recommended: true,
    chart_type: "bar",
    step_id: 2,
    dataset_id: "sample",
    dimensions: ["机构"],
    metrics: ["达成率"],
    units: { 达成率: "%" },
    description: "模拟样例，不代表真实经营数据",
    reason: "比较机构",
    data: [
      { 机构: "甲", 达成率: 61.8 },
      { 机构: "乙", 达成率: 72.3 },
    ],
  };
  await page.evaluate((value) => window.show([value]), chart);
  await expect(page.getByRole("figure")).toHaveCount(1);
  await expect(page.getByRole("application")).toBeVisible();
  await page.getByText("查看图表数据", { exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "61.8", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "达成率（%）" }),
  ).toBeVisible();
  await expect(page.getByText(chart.description)).toBeVisible();
  for (const value of [
    undefined,
    [{ ...chart, recommended: false }],
    [{ ...chart, data: [{ 机构: "甲", 达成率: null }] }],
  ]) {
    await page.evaluate((value) => window.show(value), value);
    await expect(page.getByRole("figure")).toHaveCount(0);
  }
  await expect.poll(() => errors).toEqual([]);
  console.log(
    "Chart SVG, actual values, units, limitations and invalid payload checks: PASS",
  );
} finally {
  await browser.close();
}
