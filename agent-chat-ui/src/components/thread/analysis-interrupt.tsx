import { Button } from "@/components/ui/button";
import type { Message } from "@langchain/langgraph-sdk";

import type { AnalysisInterrupt } from "@/lib/agent-inbox-interrupt";

export function AnalysisInterruptView({
  interrupt,
  lastMessage,
  disabled,
  onReply,
}: {
  interrupt: AnalysisInterrupt;
  lastMessage?: Message;
  disabled: boolean;
  onReply: (reply: string) => void;
}) {
  return (
    <section
      className="rounded-lg border p-4"
      aria-label="分析追问"
    >
      {/* 追问已保存为聊天消息时，卡片只显示补参操作。 */}
      {!(
        lastMessage?.type === "ai" &&
        lastMessage.content === interrupt.value.prompt
      ) && <p>{interrupt.value.prompt}</p>}
      {interrupt.value.kind === "scenario_selection" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {interrupt.value.candidates?.map((candidate) => (
            <div
              key={candidate.scenario_id}
              className="flex flex-col gap-1"
            >
              <Button
                disabled={disabled}
                onClick={() => onReply(candidate.scenario_id)}
              >
                {candidate.name}
                {typeof candidate.confidence === "number" &&
                  Number.isFinite(candidate.confidence) && (
                    <span>
                      {" "}
                      · 匹配 {Math.round(candidate.confidence * 100)}%
                    </span>
                  )}
              </Button>
              {candidate.reason && (
                <p className="text-muted-foreground max-w-xs text-sm">
                  {candidate.reason}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground mt-2 text-sm">
          {interrupt.value.kind === "step_clarification"
            ? "请在下方输入框回答当前步骤的问题。"
            : "请在下方输入框补充参数。"}
        </p>
      )}
    </section>
  );
}
