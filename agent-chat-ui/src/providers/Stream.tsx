import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
} from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";
import {
  uiMessageReducer,
  isUIMessage,
  isRemoveUIMessage,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { LangGraphLogoSVG } from "@/components/icons/langgraph";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ArrowRight } from "lucide-react";
import { PasswordInput } from "@/components/ui/password-input";
import { getApiKey } from "@/lib/api-key";
import { useThreads } from "./Thread";
import { toast } from "sonner";
import type { ExecutionEntry } from "@/components/thread/execution-pane";
import {
  activeBusinessValues,
  mergeMessages,
  reportMessage,
  updateReport,
  type BusinessValues,
  type ReportEvent,
  type ReportView,
} from "@/lib/report-stream";
import { completeReportSchema } from "@/lib/analysis-report";
import type { AnalysisChart } from "@/components/thread/analysis-charts";

export type StateType = {
  messages: Message[];
  ui?: UIMessage[];
  question?: string | null;
  report_template_id?: string | null;
  status?: string;
  analysis_id?: string;
  execution?: Record<string, ExecutionEntry>;
  chart_recommendations?: AnalysisChart[] | null;
};

type AnalysisDelta = {
  type: "analysis_delta";
  id: string;
  analysis_id?: string;
  text: string;
  start?: boolean;
  status?: string;
};

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
      question?: string | null;
      report_template_id?: string | null;
    };
    CustomEventType:
      | UIMessage
      | RemoveUIMessage
      | ReportEvent
      | AnalysisDelta
      | { type: "analysis_progress"; entry: ExecutionEntry };
  }
>;

type StreamContextType = ReturnType<typeof useTypedStream>;
const StreamContext = createContext<StreamContextType | undefined>(undefined);

async function sleep(ms = 4000) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkGraphStatus(
  apiUrl: string,
  apiKey: string | null,
  authScheme?: string,
): Promise<boolean> {
  try {
    const headers = new Headers();
    if (apiKey) headers.set("X-Api-Key", apiKey);
    if (authScheme) headers.set("X-Auth-Scheme", authScheme);

    const res = await fetch(`${apiUrl}/info`, {
      headers,
    });

    return res.ok;
  } catch (e) {
    console.error(e);
    return false;
  }
}

const StreamSession = ({
  children,
  apiKey,
  apiUrl,
  assistantId,
  authScheme,
}: {
  children: ReactNode;
  apiKey: string | null;
  apiUrl: string;
  assistantId: string;
  authScheme?: string;
}) => {
  const [threadId, setThreadId] = useQueryState("threadId");
  const { getThreads, setThreads } = useThreads();
  const [liveReport, setLiveReport] = useState<ReportView | null>(null);
  const [recovered, setRecovered] = useState<{
    threadId: string;
    values: BusinessValues;
  } | null>(null);
  const streamValue = useTypedStream({
    apiUrl,
    apiKey: apiKey ?? undefined,
    assistantId,
    ...(authScheme && {
      defaultHeaders: {
        "X-Auth-Scheme": authScheme,
      },
    }),
    threadId: threadId ?? null,
    fetchStateHistory: true,
    reconnectOnMount: true,
    // SDK 的数字 throttle 实际采用防抖；连续流使用零延迟批处理，避免等到流结束才刷新。
    throttle: true,
    onUpdateEvent: (updates, options) => {
      for (const update of Object.values(updates)) {
        if (!update || typeof update !== "object") continue;
        const values = update as Partial<BusinessValues>;
        if (!values.messages && !values.execution) continue;
        options.mutate((previous) => ({
          ...previous,
          messages: mergeMessages(
            previous.messages ?? [],
            values.messages ?? [],
          ),
          execution: { ...previous.execution, ...values.execution },
          status: values.status ?? previous.status,
        }));
      }
    },
    onCustomEvent: (event, options) => {
      if (event.type === "report_snapshot" || event.type === "report_step") {
        setLiveReport((previous) => updateReport(previous, event));
        return;
      }
      if (event.type === "analysis_progress") {
        options.mutate((prev) => ({
          ...prev,
          execution: { ...prev.execution, [event.entry.id]: event.entry },
        }));
        return;
      }
      if (event.type === "analysis_delta") {
        options.mutate((prev) => {
          const messages = [...(prev.messages ?? [])];
          const index = messages.findIndex(
            (message) => message.id === event.id,
          );
          const previous = index >= 0 ? messages[index] : undefined;
          const message: Message = {
            type: "ai",
            id: event.id,
            content:
              (event.start ? "" : ((previous?.content as string) ?? "")) +
              event.text,
            additional_kwargs: {
              analysis: true,
              analysis_id:
                event.analysis_id ?? previous?.additional_kwargs?.analysis_id,
              pending: true,
            },
          };
          if (index >= 0) messages[index] = message;
          else messages.push(message);
          return { ...prev, messages, status: event.status ?? prev.status };
        });
        return;
      }
      if (isUIMessage(event) || isRemoveUIMessage(event)) {
        options.mutate((prev) => {
          const ui = uiMessageReducer(prev.ui ?? [], event);
          return { ...prev, ui };
        });
      }
    },
    onThreadId: (id) => {
      setThreadId(id);
      // Refetch threads list when thread ID changes.
      // Wait for some seconds before fetching so we're able to get the new thread that was created.
      sleep().then(() => getThreads().then(setThreads).catch(console.error));
    },
  });

  const head = streamValue.history[0];
  const pendingCheckpoint = head?.next.length
    ? head.checkpoint.checkpoint_id
    : null;
  const client = streamValue.client;
  const threadLoading = streamValue.isThreadLoading;
  const loading = streamValue.isLoading;
  useEffect(() => {
    if (!threadId || threadLoading || !pendingCheckpoint) return;
    let cancelled = false;
    // 子图未结束时父图只有入口状态；恢复持久化的业务子图快照。
    client.threads
      .getState<BusinessValues>(threadId, undefined, { subgraphs: true })
      .then((snapshot) => {
        if (cancelled) return;
        const values = activeBusinessValues(snapshot);
        setRecovered({ threadId, values });
        const message = values.messages?.find(
          (item) => item.id === `${values.analysis_id}:report`,
        );
        const report = message?.additional_kwargs?.report;
        if (report) {
          setLiveReport((previous) =>
            updateReport(previous, {
              type: "report_snapshot",
              report,
            }),
          );
        }
      })
      .catch(() => {
        if (!cancelled) toast.error("恢复已保存的报告内容失败，请刷新重试。");
      });
    return () => {
      cancelled = true;
    };
  }, [client, threadId, pendingCheckpoint, threadLoading, loading]);

  let visibleValues = streamValue.values;
  if (
    pendingCheckpoint &&
    recovered?.threadId === threadId &&
    recovered.values.analysis_id === visibleValues.analysis_id
  ) {
    visibleValues = {
      ...visibleValues,
      ...recovered.values,
      messages: mergeMessages(
        recovered.values.messages ?? [],
        visibleValues.messages ?? [],
      ),
      execution: { ...recovered.values.execution, ...visibleValues.execution },
    };
  }
  if (
    liveReport?.report_id &&
    liveReport.report_id === visibleValues.analysis_id
  ) {
    const saved = visibleValues.messages?.find(
      (item) => item.id === `${liveReport.report_id}:report`,
    );
    const parsed = completeReportSchema.safeParse(
      saved?.additional_kwargs?.report,
    );
    const report =
      parsed.success && parsed.data.revision > liveReport.revision
        ? parsed.data
        : liveReport;
    visibleValues = {
      ...visibleValues,
      messages: mergeMessages(visibleValues.messages ?? [], [
        reportMessage(report),
      ]),
    };
  }
  // SDK 属性含非枚举 getter；保留原对象能力，只覆盖展示视图。
  const visibleStream: StreamContextType = Object.create(streamValue, {
    values: { value: visibleValues },
    messages: { value: visibleValues.messages ?? streamValue.messages },
  });

  useEffect(() => {
    checkGraphStatus(apiUrl, apiKey, authScheme).then((ok) => {
      if (!ok) {
        toast.error("Failed to connect to LangGraph server", {
          description: () => (
            <p>
              Please ensure your graph is running at <code>{apiUrl}</code> and
              your API key is correctly set (if connecting to a deployed graph).
            </p>
          ),
          duration: 10000,
          richColors: true,
          closeButton: true,
        });
      }
    });
  }, [apiKey, apiUrl, authScheme]);

  return (
    <StreamContext.Provider value={visibleStream}>
      {children}
    </StreamContext.Provider>
  );
};

// Default values for the form
const DEFAULT_API_URL = "http://localhost:2024";
const DEFAULT_ASSISTANT_ID = "agent";
const AGENT_BUILDER_AUTH_SCHEME = "langsmith-api-key";

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  // Get environment variables
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID;
  const envAuthScheme: string | undefined = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  // Use URL params with env var fallbacks
  const [apiUrl, setApiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId, setAssistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });
  const [authScheme, setAuthScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });
  const [isAgentBuilder, setIsAgentBuilder] = useState(
    () =>
      (authScheme || envAuthScheme || "").toLowerCase() ===
      AGENT_BUILDER_AUTH_SCHEME,
  );

  // For API key, use localStorage with env var fallback
  const [apiKey, _setApiKey] = useState(() => {
    const storedKey = getApiKey();
    return storedKey || "";
  });

  const setApiKey = (key: string) => {
    window.localStorage.setItem("lg:chat:apiKey", key);
    _setApiKey(key);
  };

  // Determine final values to use, prioritizing URL params then env vars
  const finalApiUrl = apiUrl || envApiUrl;
  const finalAssistantId = assistantId || envAssistantId;
  const finalAuthScheme = authScheme || envAuthScheme || "";

  // Show the form if we: don't have an API URL, or don't have an assistant ID
  if (!finalApiUrl || !finalAssistantId) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center p-4">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex max-w-3xl flex-col rounded-lg border shadow-lg">
          <div className="mt-14 flex flex-col gap-2 border-b p-6">
            <div className="flex flex-col items-start gap-2">
              <LangGraphLogoSVG className="h-7" />
              <h1 className="text-xl font-semibold tracking-tight">
                Agent Chat
              </h1>
            </div>
            <p className="text-muted-foreground">
              Welcome to Agent Chat! Before you get started, you need to enter
              the URL of the deployment and the assistant / graph ID.
            </p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();

              const form = e.target as HTMLFormElement;
              const formData = new FormData(form);
              const apiUrl = formData.get("apiUrl") as string;
              const assistantId = formData.get("assistantId") as string;
              const apiKey = formData.get("apiKey") as string;

              setApiUrl(apiUrl);
              setApiKey(apiKey);
              setAssistantId(assistantId);
              setAuthScheme(isAgentBuilder ? AGENT_BUILDER_AUTH_SCHEME : "");

              form.reset();
            }}
            className="bg-muted/50 flex flex-col gap-6 p-6"
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="apiUrl">
                Deployment URL<span className="text-rose-500">*</span>
              </Label>
              <p className="text-muted-foreground text-sm">
                This is the URL of your LangGraph deployment. Can be a local, or
                production deployment.
              </p>
              <Input
                id="apiUrl"
                name="apiUrl"
                className="bg-background"
                defaultValue={apiUrl || DEFAULT_API_URL}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="assistantId">
                Assistant / Graph ID<span className="text-rose-500">*</span>
              </Label>
              <p className="text-muted-foreground text-sm">
                This is the ID of the graph (can be the graph name), or
                assistant to fetch threads from, and invoke when actions are
                taken.
              </p>
              <Input
                id="assistantId"
                name="assistantId"
                className="bg-background"
                defaultValue={assistantId || DEFAULT_ASSISTANT_ID}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="apiKey">LangSmith API Key</Label>
              <p className="text-muted-foreground text-sm">
                This is <strong>NOT</strong> required if using a local LangGraph
                server. This value is stored in your browser's local storage and
                is only used to authenticate requests sent to your LangGraph
                server.
              </p>
              <PasswordInput
                id="apiKey"
                name="apiKey"
                defaultValue={apiKey ?? ""}
                className="bg-background"
                placeholder="lsv2_pt_..."
              />
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="agentBuilderEnabled">
                    Built with Agent Builder
                  </Label>
                  <p className="text-muted-foreground text-sm">
                    Enable this for Agent Builder deployments.
                  </p>
                </div>
                <Switch
                  id="agentBuilderEnabled"
                  checked={isAgentBuilder}
                  onCheckedChange={setIsAgentBuilder}
                />
              </div>
            </div>

            <div className="mt-2 flex justify-end">
              <Button
                type="submit"
                size="lg"
              >
                Continue
                <ArrowRight className="size-5" />
              </Button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <StreamSession
      apiKey={apiKey}
      apiUrl={finalApiUrl}
      assistantId={finalAssistantId}
      authScheme={finalAuthScheme || undefined}
    >
      {children}
    </StreamSession>
  );
};

// Create a custom hook to use the context
export const useStreamContext = (): StreamContextType => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
