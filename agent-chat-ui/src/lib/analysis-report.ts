import type { Message } from "@langchain/langgraph-sdk";
import { z } from "zod";
import { getContentString } from "@/components/thread/utils";

export const completeReportSchema = z.object({
  report_id: z.string().optional(),
  status: z.enum(["generating", "complete"]).default("complete"),
  revision: z.number().int().nonnegative().default(0),
  title: z.string(),
  markdown: z.string().min(1),
  sections: z.array(
    z.object({
      section_id: z.string(),
      markdown: z.string(),
      charts: z.array(z.unknown()),
      heading: z.string().optional(),
      table_markdown: z.string().optional(),
      blocks: z
        .array(
          z.object({
            step_id: z.number().int(),
            text: z.string(),
            status: z.enum(["pending", "generating", "complete", "error"]),
          }),
        )
        .optional(),
    }),
  ),
});

export function getAnalysisReport(messages: Message[], analysisId: string) {
  const prefix = `${analysisId}:`;
  const complete = messages.find(
    (message) => message.type === "ai" && message.id === `${prefix}report`,
  );
  const parsed = completeReportSchema.safeParse(
    complete?.additional_kwargs?.report,
  );
  if (parsed.success && parsed.data.status !== "complete") return null;
  if (parsed.success && complete?.additional_kwargs?.pending !== true) {
    const question = messages.find(
      (message) => message.type === "human" && message.id === analysisId,
    );
    return {
      title: parsed.data.title,
      markdown: parsed.data.markdown,
      question: question ? getContentString(question.content).trim() : "",
    };
  }
  const sections = messages.filter((message) => {
    if (message.type !== "ai" || !message.id?.startsWith(prefix)) return false;
    return /^(step:\d+|summary|charts)$/.test(message.id.slice(prefix.length));
  });
  const summary = sections.find((message) => message.id === `${prefix}summary`);
  const charts = sections.find((message) => message.id === `${prefix}charts`);
  const steps = sections.filter((message) =>
    message.id?.startsWith(`${prefix}step:`),
  );
  // 图表节点先保存标题占位，只有最终正文到达才表示报告完整。
  if (
    !summary ||
    !charts ||
    !steps.length ||
    sections.some((message) => message.additional_kwargs?.pending === true) ||
    !getContentString(charts.content).trim().includes("\n\n")
  )
    return null;
  steps.sort(
    (a, b) =>
      Number(a.id!.slice(`${prefix}step:`.length)) -
      Number(b.id!.slice(`${prefix}step:`.length)),
  );
  const question = messages.find(
    (message) => message.type === "human" && message.id === analysisId,
  );
  return {
    title: "经营分析报告",
    question: question ? getContentString(question.content).trim() : "",
    markdown: [...steps, summary, charts]
      .map((message) => getContentString(message.content))
      .join("\n\n"),
  };
}
