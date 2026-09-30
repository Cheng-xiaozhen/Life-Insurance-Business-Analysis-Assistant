import type { Message, ThreadState } from "@langchain/langgraph-sdk";
import { z } from "zod";
import { completeReportSchema } from "@/lib/analysis-report";

export type ReportView = z.infer<typeof completeReportSchema>;
export type ReportEvent =
  | { type: "report_snapshot"; report: unknown }
  | {
      type: "report_step";
      report_id: string;
      section_id: string;
      step_id: number;
      text: string;
      status: "generating" | "error";
    };

export function updateReport(
  previous: ReportView | null,
  event: ReportEvent,
): ReportView | null {
  if (event.type === "report_snapshot") {
    const parsed = completeReportSchema.safeParse(event.report);
    if (!parsed.success) return previous;
    const next = parsed.data;
    if (
      previous &&
      previous.report_id === next.report_id &&
      previous.revision >= next.revision
    )
      return previous;
    return next;
  }
  if (
    !previous ||
    previous.report_id !== event.report_id ||
    previous.status === "complete"
  )
    return previous;
  return {
    ...previous,
    sections: previous.sections.map((section) =>
      section.section_id !== event.section_id
        ? section
        : {
            ...section,
            blocks: section.blocks?.map((block) =>
              block.step_id !== event.step_id || block.status === "complete"
                ? block
                : { ...block, text: event.text, status: event.status },
            ),
          },
    ),
  };
}

export function mergeMessages(
  previous: Message[],
  incoming: Message[],
): Message[] {
  const messages = [...previous];
  for (const message of incoming) {
    const index = messages.findIndex((item) => item.id === message.id);
    if (index < 0) messages.push(message);
    else messages[index] = message;
  }
  return messages;
}

export type BusinessValues = {
  messages: Message[];
  analysis_id?: string;
  status?: string;
  execution?: Record<
    string,
    {
      id: string;
      analysis_id: string;
      label: string;
      state: "running" | "done" | "waiting" | "error";
      message_id?: string;
    }
  >;
};

export function activeBusinessValues(
  snapshot: ThreadState<BusinessValues>,
): BusinessValues {
  let values = snapshot.values;
  for (const task of snapshot.tasks ?? []) {
    if (!task.state) continue;
    const child = activeBusinessValues(
      task.state as ThreadState<BusinessValues>,
    );
    if (
      child.analysis_id === values.analysis_id &&
      Array.isArray(child.messages)
    ) {
      values = {
        ...values,
        ...child,
        messages: mergeMessages(values.messages ?? [], child.messages),
      };
    }
  }
  return values;
}

export function reportMessage(report: ReportView): Message {
  return {
    type: "ai",
    id: `${report.report_id}:report`,
    content: report.markdown,
    additional_kwargs: {
      analysis: true,
      analysis_id: report.report_id,
      report,
    },
  };
}
