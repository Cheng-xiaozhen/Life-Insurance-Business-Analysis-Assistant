// Run: node scripts/check-report-download.mjs [optional-output.docx]
import assert from "node:assert/strict";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { chromium, expect } from "@playwright/test";
const require = createRequire(import.meta.url);
const JSZip = createRequire(require.resolve("docx"))("jszip");
const root = fileURLToPath(new URL("../", import.meta.url));
const { outputFiles } = await build({
  absWorkingDir: root,
  stdin: {
    resolveDir: root,
    loader: "tsx",
    contents: `
    import React from "react";
    import { createRoot } from "react-dom/client";
    import { ReportDownload } from "./src/components/thread/report-download";
    import { getAnalysisReport } from "./src/lib/analysis-report";
    const root = createRoot(document.getElementById("root"));
    window.show = (props) => root.render(React.createElement(ReportDownload, props));
    window.report = getAnalysisReport;
  `,
  },
  bundle: true,
  format: "iife",
  write: false,
});
const temp = await mkdtemp(join(tmpdir(), "report-download-"));
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: outputFiles[0].text });
  const ai = (id, content) => ({
    type: "ai",
    id,
    content,
    additional_kwargs: { analysis: true, reasoning: "内部思考不能导出" },
  });
  const props = {
    analysisId: "q1",
    messages: [
      { type: "human", id: "q1", content: "2026年8月标保情况" },
      ai("q1:clarify:q1", "补参提示不能导出"),
      ai(
        "q1:step:2",
        "### 步骤 2 机构分析\n\n1. 核对甲机构\n2. 核对乙机构\n\n- 跟进差距\n  - 复核统计口径",
      ),
      ai(
        "q1:step:1",
        "### 步骤 1 标保达成情况\n\n本月**标保达成率为80%**，较上月改善。\n\n| 机构 | 标保 | 达成率 |\n| --- | ---: | ---: |\n| 甲机构 | 100万元 | 80% |\n| 乙机构 | 120万元 | 90% |",
      ),
      ai(
        "q1:summary",
        "### 场景总结\n\n整体改善，但仍需关注机构差异。\n\n> 数据范围为全系统。",
      ),
      ai("q2:summary", "另一轮分析不能导出"),
    ],
  };
  await page.evaluate((props) => window.show(props), props);
  await expect(page.getByRole("button", { name: "下载报告" })).toHaveCount(0);
  props.messages.push(ai("q1:charts", "### 图表推荐\n\n"));
  await page.evaluate((props) => window.show(props), props);
  await expect(page.getByRole("button", { name: "下载报告" })).toHaveCount(0);
  props.messages.at(-1).content =
    "### 图表推荐\n\n推荐柱状图，比较各机构标保。";
  props.messages.at(-1).additional_kwargs.pending = true;
  await page.evaluate((props) => window.show(props), props);
  await expect(page.getByRole("button", { name: "下载报告" })).toHaveCount(0);
  delete props.messages.at(-1).additional_kwargs.pending;
  await page.evaluate((props) => window.show(props), props);
  await expect(page.getByRole("button", { name: "下载报告" })).toBeVisible();
  const ready = await page.evaluate(
    (props) => window.report(props.messages, props.analysisId),
    props,
  );
  assert.ok(
    ready.markdown.indexOf("步骤 1") < ready.markdown.indexOf("步骤 2"),
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载报告" }).click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "2026年8月标保情况_分析报告.docx");
  const path = process.argv[2]
    ? resolve(process.argv[2])
    : join(temp, "report.docx");
  await download.saveAs(path);
  const zip = await JSZip.loadAsync(await readFile(path));
  const xml = await zip.file("word/document.xml").async("string");
  assert.ok(
    xml.includes("整体改善") &&
      xml.includes("甲机构") &&
      xml.includes("图表推荐"),
  );
  assert.ok(
    xml.includes("<w:tbl>") &&
      xml.includes("<w:numPr>") &&
      xml.includes("<w:b/>") &&
      xml.includes("<w:tblHeader"),
  );
  assert.ok(!xml.includes("不能导出"));
  assert.deepEqual(errors, []);
  console.log(
    "Word download: browser click, DOCX structure, tables/lists, completion gating and turn isolation PASS",
  );
} finally {
  await browser.close();
  await rm(temp, { recursive: true, force: true });
}
