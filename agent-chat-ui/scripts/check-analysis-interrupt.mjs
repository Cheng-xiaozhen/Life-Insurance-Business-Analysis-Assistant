// Run from agent-chat-ui: node scripts/check-analysis-interrupt.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const { outputFiles } = await build({
  absWorkingDir: fileURLToPath(new URL("../", import.meta.url)),
  entryPoints: ["src/components/thread/analysis-interrupt.tsx"],
  bundle: true,
  packages: "external",
  platform: "node",
  format: "cjs",
  write: false,
});
const module = { exports: {} };
new Function("require", "module", "exports", outputFiles[0].text)(
  createRequire(import.meta.url),
  module,
  module.exports,
);
const { AnalysisInterruptView } = module.exports;
const prompt = "请补充或修正以下参数：年份；月份";
const lastMessage = { type: "ai", content: prompt };
const render = (kind, message = lastMessage, text = prompt) =>
  renderToStaticMarkup(
    createElement(AnalysisInterruptView, {
      interrupt: {
        id: "interrupt-1",
        value: {
          kind,
          prompt: text,
          candidates: [{ scenario_id: "premium", name: "标保" }],
        },
      },
      lastMessage: message,
      disabled: false,
      onReply: () => {},
    }),
  );

assert.ok(!render("slot_completion").includes(prompt));
assert.ok(render("slot_completion").includes("请在下方输入框补充参数。"));
assert.ok(!render("scenario_selection").includes(prompt));
assert.ok(render("scenario_selection").includes("标保</button>"));
assert.ok(render("slot_completion", null).includes(prompt));
assert.ok(
  render("slot_completion", { type: "human", content: prompt }).includes(
    prompt,
  ),
);
assert.ok(
  render("slot_completion", lastMessage, "请用非空文本补充参数。").includes(
    "请用非空文本补充参数。",
  ),
);
assert.ok(render("step_clarification").includes("请在下方输入框回答当前步骤的问题。"));
console.log("Analysis interrupt rendering checks passed.");
