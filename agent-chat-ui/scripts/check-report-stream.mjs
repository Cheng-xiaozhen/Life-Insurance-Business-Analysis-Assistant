// With Next dev running: node scripts/check-report-stream.mjs
import { chromium, expect } from "@playwright/test";

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  let recovery = null;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      const url =
        typeof input === "string" ? input : (input.url ?? String(input));
      if (!url.includes("localhost:5519/") || !url.endsWith("/runs/stream"))
        return original(input, init);
      const request = JSON.parse(init.body);
      return new Response(
        new ReadableStream({
          start(controller) {
            window.reportFeed = { request, controller };
            window.emitReport = (event, data) =>
              controller.enqueue(
                new TextEncoder().encode(
                  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
                ),
              );
            window.emitReport("metadata", { run_id: "report-run" });
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      );
    };
  });
  await page.route("http://localhost:5519/**", async (route) => {
    const url = new URL(route.request().url());
    let body = [];
    if (url.pathname.endsWith("/info")) body = {};
    else if (
      url.pathname.endsWith("/threads") &&
      route.request().method() === "POST"
    )
      body = { thread_id: "report-thread" };
    else if (recovery && url.pathname.endsWith("/history"))
      body = [
        {
          ...recovery,
          tasks: recovery.tasks.map((task) => ({ ...task, state: null })),
        },
      ];
    else if (recovery && url.pathname.endsWith("/state")) body = recovery;
    else if (url.pathname.endsWith("/report-thread"))
      body = { thread_id: "report-thread", status: "interrupted" };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.route("**/api/report-templates", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        reports: [{ code: "monthly", name: "月度经营分析" }],
      }),
    }),
  );
  await page.goto(
    `${process.env.SCENARIOS_URL ?? "http://localhost:3000"}/?apiUrl=http%3A%2F%2Flocalhost%3A5519&assistantId=agent`,
  );
  await page.getByRole("button", { name: "选择报告模板", exact: true }).click();
  await page.getByRole("button", { name: "月度经营分析", exact: true }).click();
  await page
    .getByRole("textbox", { name: "分析问题或补充参数" })
    .fill("生成月度报告");
  await page.getByRole("button", { name: "生成报告", exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!window.reportFeed)).toBe(true);
  const human = await page.evaluate(() =>
    window.reportFeed.request.input.messages.at(-1),
  );
  const emit = (event, data) =>
    page.evaluate(({ event, data }) => window.emitReport(event, data), {
      event,
      data,
    });
  const initial = {
    messages: [human],
    analysis_id: human.id,
    status: "正在生成报告",
    execution: {},
  };
  const report = {
    report_id: human.id,
    title: "月度经营分析",
    status: "generating",
    revision: 0,
    markdown: "# 月度经营分析",
    sections: [
      {
        section_id: "1",
        heading: "## 标保概况",
        markdown: "## 标保概况",
        charts: [],
        table_markdown: "",
        blocks: [{ step_id: 1, text: "", status: "pending" }],
      },
      {
        section_id: "2",
        heading: "## 人力概况",
        markdown: "## 人力概况",
        charts: [],
        table_markdown: "",
        blocks: [],
      },
      {
        section_id: "2.1",
        heading: "### 活动人力",
        markdown: "### 活动人力",
        charts: [],
        table_markdown: "",
        blocks: [
          { step_id: 2, text: "", status: "pending" },
          { step_id: 3, text: "", status: "pending" },
        ],
      },
    ],
  };
  await emit("values", initial);
  await emit("custom|report_generation:test", {
    type: "report_snapshot",
    report,
  });
  await expect(
    page.getByRole("heading", { name: "标保概况", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "活动人力", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "下载报告" })).toHaveCount(0);
  await page.evaluate(() => {
    window.savedHeading = [...document.querySelectorAll("h2")].find(
      (item) => item.textContent === "标保概况",
    );
  });
  const delta = {
    type: "report_step",
    report_id: human.id,
    section_id: "1",
    step_id: 1,
    status: "generating",
  };
  await emit("custom", { ...delta, text: "标保正文逐渐生成" });
  await emit("custom", { ...delta, text: "标保正文逐渐生成" }); // 重放不能追加两次。
  await expect(page.getByText("标保正文逐渐生成", { exact: true })).toHaveCount(
    1,
  );
  report.revision = 1;
  report.sections[0].blocks[0] = {
    step_id: 1,
    text: "标保正文逐渐生成",
    status: "complete",
  };
  await emit("custom", { type: "report_snapshot", report });
  await emit("custom", { ...delta, text: "旧片段不能覆盖已提交正文" });
  await expect(page.getByText("旧片段不能覆盖已提交正文")).toHaveCount(0);
  await emit("custom", {
    ...delta,
    section_id: "2.1",
    step_id: 2,
    text: "活动人力正文",
  });
  await expect(page.getByText("活动人力正文", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.savedHeading.isConnected)).toBe(true);

  // 模拟刷新：父图仍停在业务子图入口，正文只存在于子图检查点。
  const checkpoint = {
    thread_id: "report-thread",
    checkpoint_id: "root-checkpoint",
    checkpoint_ns: "",
    checkpoint_map: null,
  };
  const savedMessage = {
    type: "ai",
    id: `${human.id}:report`,
    content: report.markdown,
    additional_kwargs: { analysis: true, analysis_id: human.id, report },
  };
  const base = {
    checkpoint,
    metadata: {},
    created_at: "2026-09-30T00:00:00Z",
    parent_checkpoint: null,
  };
  recovery = {
    ...base,
    values: initial,
    next: ["report_generation"],
    tasks: [
      {
        id: "task",
        name: "report_generation",
        error: "模拟失败",
        interrupts: [],
        checkpoint: null,
        state: {
          ...base,
          values: { ...initial, messages: [human, savedMessage] },
          next: ["analyze_report_step"],
          tasks: [],
        },
      },
    ],
  };
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "标保概况", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("标保正文逐渐生成", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("活动人力正文", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下载报告" })).toHaveCount(0);
  await page
    .getByRole("region", { name: "Agent 执行过程" })
    .getByRole("button")
    .first()
    .click();
  await page.getByRole("button", { name: "从失败处重试", exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!window.reportFeed)).toBe(true);
  await emit("custom", {
    ...delta,
    section_id: "2.1",
    step_id: 2,
    text: "活动人力完成正文",
  });
  await expect(
    page.getByText("活动人力完成正文", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    window.savedHeading = [...document.querySelectorAll("h2")].find(
      (item) => item.textContent === "标保概况",
    );
  });
  report.revision = 5;
  report.status = "complete";
  report.sections[2].blocks = [
    { step_id: 2, text: "活动人力完成正文", status: "complete" },
    { step_id: 3, text: "第二段正文", status: "complete" },
  ];
  report.markdown += "\n\n标保正文逐渐生成\n\n活动人力完成正文\n\n第二段正文";
  await emit("custom", { type: "report_snapshot", report });
  await expect(page.getByRole("button", { name: "下载报告" })).toBeVisible();
  expect(await page.evaluate(() => window.savedHeading.isConnected)).toBe(true);
  await emit("values", {
    ...initial,
    status: "已完成",
    messages: [
      human,
      {
        ...savedMessage,
        content: report.markdown,
        additional_kwargs: { ...savedMessage.additional_kwargs, report },
      },
    ],
  });
  recovery = null;
  await emit("end", null);
  await page.evaluate(() => window.reportFeed.controller.close());
  await expect(page.getByText("第二段正文", { exact: true })).toHaveCount(1);
  expect(errors).toEqual([]);
  console.log(
    "Report stream: outline, cumulative text, committed results, reload from subgraph, retry, stable headings and download gate PASS",
  );
} finally {
  await browser.close();
}
