import type { Message } from "@langchain/langgraph-sdk";
import { getContentString } from "@/components/thread/utils";

export function getAnalysisReport(messages: Message[], analysisId: string) {
  const prefix = `${analysisId}:`;
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
