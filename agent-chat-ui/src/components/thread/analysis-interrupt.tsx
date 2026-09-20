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
            <Button
              key={candidate.scenario_id}
              disabled={disabled}
              onClick={() => onReply(candidate.scenario_id)}
            >
              {candidate.name}
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground mt-2 text-sm">
          请在下方输入框补充参数。
        </p>
      )}
    </section>
  );
}
