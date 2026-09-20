import { useId, useState, type ReactNode } from "react";
import {
  Check,
  ChevronDown,
  CircleAlert,
  LoaderCircle,
  Pause,
} from "lucide-react";
import type { Message } from "@langchain/langgraph-sdk";

export type ExecutionEntry = {
  id: string;
  analysis_id: string;
  label: string;
  state: "running" | "done" | "waiting" | "error";
  message_id?: string;
};

export function ExecutionPane({
  entries,
  messages,
  running,
  status,
  actions,
}: {
  entries: ExecutionEntry[];
  messages: Message[];
  running: boolean;
  status: string;
  actions?: ReactNode;
}) {
  const [open, setOpen] = useState(running);
  const contentId = useId();
  const latest = entries[entries.length - 1];
  return (
    <section
      aria-label="Agent 执行过程"
      className="bg-muted/30 rounded-xl border"
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 p-4 text-left text-sm"
      >
        {running ? (
          <LoaderCircle
            aria-hidden="true"
            className="size-4 shrink-0 animate-spin motion-reduce:animate-none"
          />
        ) : (
          <ChevronDown
            aria-hidden="true"
            className={`size-4 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`}
          />
        )}
        <span className="shrink-0 font-medium">思考过程</span>
        <span
          role="status"
          className="text-muted-foreground truncate"
        >
          {running ? (latest?.label ?? status) : status}
        </span>
      </button>
      {open && (
        <div
          id={contentId}
          className="max-h-[28rem] overflow-y-auto border-t p-4"
        >
          <ol className="space-y-4">
            {entries.map((entry, index) => {
              const reasoning = messages.find(
                (message) => message.id === entry.message_id,
              )?.additional_kwargs?.reasoning;
              const active = running && entry.state === "running";
              const waiting =
                (entry.state === "waiting" && index === entries.length - 1) ||
                (entry.state === "running" && !running);
              return (
                <li
                  key={entry.id}
                  className="flex items-start gap-3 text-sm"
                >
                  {active ? (
                    <LoaderCircle
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0 animate-spin motion-reduce:animate-none"
                    />
                  ) : entry.state === "error" ? (
                    <CircleAlert
                      aria-hidden="true"
                      className="text-destructive mt-0.5 size-4 shrink-0"
                    />
                  ) : waiting ? (
                    <Pause
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0"
                    />
                  ) : (
                    <Check
                      aria-hidden="true"
                      className="text-muted-foreground mt-0.5 size-4 shrink-0"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p>
                      {entry.label}
                      {entry.state === "error" ? "（失败）" : ""}
                      {entry.state === "running" && !running
                        ? "（已暂停）"
                        : ""}
                    </p>
                    {typeof reasoning === "string" && reasoning && (
                      <details className="text-muted-foreground mt-2">
                        <summary className="cursor-pointer">模型思考</summary>
                        <div className="mt-2 leading-6 whitespace-pre-wrap">
                          {reasoning}
                        </div>
                      </details>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {actions && <div className="mt-4">{actions}</div>}
        </div>
      )}
    </section>
  );
}
