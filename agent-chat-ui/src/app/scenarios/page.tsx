"use client";

import { Suspense, useEffect, useId, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ChevronRight,
  Plus,
  X,
} from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const stepSchema = z.object({
  text: z.string().trim().min(1),
  metrics: z.array(z.string()),
  mode: z.string(),
  queryParams: z
    .record(z.string(), z.union([z.string(), z.number().int()]))
    .optional(),
});
const scenarioSchema = z.object({
  code: z.string().trim().min(1),
  name: z.string().trim().min(1),
  channel: z.string(),
  period: z.string(),
  target: z.string(),
  purpose: z.string(),
  keywords: z.array(z.string()),
  steps: z.array(stepSchema).min(1),
});
type Scenario = z.infer<typeof scenarioSchema>;
const fields = [
  ["code", "场景编码"],
  ["name", "场景名称"],
  ["channel", "渠道类型"],
  ["period", "时间维度"],
  ["target", "分析对象"],
  ["purpose", "分析目的"],
] as const;
const blank: Scenario = {
  code: "",
  name: "",
  channel: "",
  period: "",
  target: "",
  purpose: "",
  keywords: [],
  steps: [{ text: "", metrics: [], mode: "" }],
};

function TagInput({
  name,
  label,
  defaultValue,
}: {
  name: string;
  label: string;
  defaultValue: string[];
}) {
  const id = useId();
  const [tags, setTags] = useState(defaultValue);
  const [input, setInput] = useState("");
  function add() {
    const values = input
      .split(/[\n,，;；]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    setTags((current) => [...new Set([...current, ...values])]);
    setInput("");
  }
  return (
    <div className="grid min-w-0 content-start gap-2 text-sm">
      <label
        htmlFor={id}
        className="font-medium"
      >
        {label}
      </label>
      {tags.length > 0 && (
        <ul
          aria-label={`${label}标签`}
          className="flex flex-wrap gap-2"
        >
          {tags.map((tag) => (
            <li
              key={tag}
              className="flex max-w-full items-center gap-1 rounded-md bg-teal-50 py-1 pr-1 pl-2.5 text-[#2F6868]"
            >
              <input
                type="hidden"
                name={name}
                value={tag}
              />
              <span className="min-w-0 break-all">{tag}</span>
              <button
                type="button"
                aria-label={`删除${label}：${tag}`}
                onClick={() =>
                  setTags((current) => current.filter((value) => value !== tag))
                }
                className="shrink-0 rounded p-1 hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <X
                  aria-hidden="true"
                  className="size-3.5"
                />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <Input
          id={id}
          name={name}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="输入新值，按回车添加"
          aria-describedby={`${id}-hint`}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              add();
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={!input.trim()}
          aria-label={`添加${label}`}
          onClick={add}
        >
          添加
        </Button>
      </div>
      <p
        id={`${id}-hint`}
        className="text-muted-foreground text-xs"
      >
        可用逗号分隔添加多个值，重复值自动合并。
      </p>
    </div>
  );
}

function ScenarioEditor({
  scenario,
  onSave,
  onCancel,
}: {
  scenario: Scenario;
  onSave: (value: Scenario) => Promise<string | undefined>;
  onCancel: () => void;
}) {
  const [steps, setSteps] = useState(() =>
    scenario.steps.map((step, id) => ({ ...step, id })),
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = (name: string) => String(form.get(name) ?? "").trim();
    const list = (name: string) => [
      ...new Set(
        form
          .getAll(name)
          .flatMap((entry) => String(entry).split(/[\n,，;；]+/))
          .map((s) => s.trim())
          .filter(Boolean),
      ),
    ];
    const parsed = scenarioSchema.safeParse({
      ...Object.fromEntries(fields.map(([key]) => [key, value(key)])),
      keywords: list("keywords"),
      steps: steps.map(({ id, queryParams }) => ({
        text: value(`text-${id}`),
        metrics: list(`metrics-${id}`),
        mode: value(`mode-${id}`),
        queryParams,
      })),
    });
    if (!parsed.success) {
      setError("请填写场景编码、场景名称和每个步骤的分析内容。");
      return;
    }
    setSaving(true);
    try {
      setError((await onSave(parsed.data)) ?? "");
    } finally {
      setSaving(false);
    }
  }
  function move(index: number, offset: number) {
    setSteps((current) => {
      const next = [...current];
      [next[index], next[index + offset]] = [next[index + offset], next[index]];
      return next;
    });
  }
  return (
    <form
      onSubmit={save}
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="overflow-y-auto px-5 py-6 sm:px-8">
        <fieldset
          disabled={saving}
          className="min-w-0 space-y-8"
        >
          <section aria-labelledby="basic-title">
            <h2
              id="basic-title"
              className="mb-5 text-base font-semibold"
            >
              基本信息
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {fields.map(([key, label]) => (
                <label
                  key={key}
                  className="grid gap-2 text-sm font-medium"
                >
                  <span>
                    {label}
                    {(key === "code" || key === "name") && (
                      <span className="ml-1 text-red-600">*</span>
                    )}
                  </span>
                  <Input
                    name={key}
                    defaultValue={scenario[key]}
                    required={key === "code" || key === "name"}
                    placeholder={`请输入${label}`}
                  />
                </label>
              ))}
              <div className="sm:col-span-2">
                <TagInput
                  label="触发关键词"
                  name="keywords"
                  defaultValue={scenario.keywords}
                />
              </div>
            </div>
          </section>
          <section
            aria-labelledby="steps-title"
            className="border-t pt-6"
          >
            <div className="mb-5 flex items-center justify-between gap-2">
              <h2
                id="steps-title"
                className="text-base font-semibold"
              >
                分析思路{" "}
                <span className="text-muted-foreground ml-2 text-sm font-normal">
                  {steps.length} 个步骤
                </span>
              </h2>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  setSteps((current) => [
                    ...current,
                    {
                      id: Math.max(...current.map((s) => s.id)) + 1,
                      text: "",
                      metrics: [],
                      mode: "",
                    },
                  ])
                }
              >
                <Plus aria-hidden="true" />
                添加步骤
              </Button>
            </div>
            <div className="space-y-4">
              {steps.map((step, index) => (
                <fieldset
                  key={step.id}
                  className="bg-muted/20 min-w-0 rounded-xl border p-4"
                >
                  <legend className="px-2 text-sm font-semibold">
                    步骤 {index + 1}
                  </legend>
                  <div className="mb-3 flex justify-end gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`上移步骤 ${index + 1}`}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`下移步骤 ${index + 1}`}
                      disabled={index === steps.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={steps.length === 1}
                      onClick={() =>
                        setSteps((current) =>
                          current.filter((s) => s.id !== step.id),
                        )
                      }
                    >
                      删除步骤 {index + 1}
                    </Button>
                  </div>
                  <label className="grid gap-2 text-sm font-medium">
                    分析步骤{" "}
                    <Textarea
                      name={`text-${step.id}`}
                      defaultValue={step.text}
                      required
                      placeholder="描述这一步需要分析的内容"
                      rows={3}
                    />
                  </label>
                  <div className="mt-4 grid grid-cols-1 gap-4">
                    <TagInput
                      label="关联指标"
                      name={`metrics-${step.id}`}
                      defaultValue={step.metrics}
                    />
                    <label className="flex flex-col gap-2 text-sm font-medium">
                      分析模式（可选）
                      <Input
                        name={`mode-${step.id}`}
                        defaultValue={step.mode}
                        placeholder="自由输入，例如：趋势分析"
                      />
                    </label>
                  </div>
                </fieldset>
              ))}
            </div>
          </section>
        </fieldset>
      </div>
      <footer className="bg-background flex flex-wrap items-center justify-end gap-3 border-t px-5 py-4 sm:px-8">
        {error && (
          <p
            role="alert"
            className="mr-auto text-sm text-red-600"
          >
            {error}
          </p>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={saving}
          onClick={onCancel}
        >
          取消
        </Button>
        <Button
          type="submit"
          disabled={saving}
          variant="brand"
        >
          {saving ? "保存中…" : "保存场景"}
        </Button>
      </footer>
    </form>
  );
}

function ScenariosPage() {
  const searchParams = useSearchParams();
  const chatHref = searchParams.size ? `/?${searchParams.toString()}` : "/";
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [ready, setReady] = useState(false);
  const [editing, setEditing] = useState<{
    index: number;
    scenario: Scenario;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  async function load() {
    try {
      const response = await fetch("/api/scenarios", { cache: "no-store" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      setScenarios(z.array(scenarioSchema).parse(result.scenarios));
      setReady(true);
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "加载场景失败，请重试。",
      );
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function save(scenario: Scenario): Promise<string | undefined> {
    if (!editing) return;
    setSaving(true);
    try {
      const response = await fetch("/api/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          originalCode: editing.index === -1 ? null : editing.scenario.code,
        }),
      });
      const result = await response.json();
      if (!response.ok) return result.error ?? "保存失败，请重试。";
      const saved = scenarioSchema.parse(result.scenario);
      setScenarios((current) =>
        editing.index === -1
          ? [...current, saved]
          : current.map((s, i) => (i === editing.index ? saved : s)),
      );
      setEditing(null);
      setNotice(`已保存「${saved.name}」。`);
    } catch {
      return "保存失败，请检查服务连接后重试。";
    } finally {
      setSaving(false);
    }
  }
  return (
    <main
      lang="zh-CN"
      className="min-h-screen bg-slate-50/60"
    >
      <header className="bg-background border-b px-5 py-4 sm:px-8">
        <Button
          asChild
          variant="ghost"
          size="sm"
        >
          <Link href={chatHref}>
            <ArrowLeft aria-hidden="true" />
            返回分析对话
          </Link>
        </Button>
      </header>
      <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="mb-10 flex flex-wrap items-start justify-between gap-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              分析场景管理
            </h1>
            <p className="text-muted-foreground mt-3 text-sm">
              查看和维护场景模板，定义分析所需的基本信息与分析思路。
            </p>
          </div>
          <Button
            variant="brand"
            disabled={!ready}
            onClick={() => setEditing({ index: -1, scenario: blank })}
          >
            <Plus aria-hidden="true" />
            新增场景
          </Button>
        </div>
        <div className="mb-4 flex items-center gap-3">
          <h2 className="font-medium">全部场景</h2>
          <span className="bg-muted text-muted-foreground rounded-full px-2.5 py-0.5 text-xs">
            {scenarios.length}
          </span>
        </div>
        {!ready && !loadError && <p role="status">正在加载场景…</p>}
        {loadError && (
          <div
            role="alert"
            className="mb-4 text-sm text-red-600"
          >
            {loadError}
            <Button
              variant="outline"
              className="ml-3"
              onClick={() => {
                setReady(false);
                setLoadError("");
                void load();
              }}
            >
              重新加载
            </Button>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {scenarios.map((scenario, index) => (
            <button
              key={scenario.code}
              disabled={!ready}
              onClick={() => setEditing({ index, scenario })}
              className="bg-background flex min-h-24 items-center justify-between gap-4 rounded-xl border p-6 text-left font-medium transition-colors hover:border-[#2F6868] hover:bg-teal-50/40 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#2F6868]"
            >
              <span className="min-w-0 break-words">{scenario.name}</span>
              <ChevronRight
                aria-hidden="true"
                className="text-muted-foreground size-4 shrink-0"
              />
            </button>
          ))}
        </div>
        {ready && scenarios.length === 0 && (
          <p className="text-muted-foreground rounded-xl border border-dashed p-10 text-center">
            暂无场景，点击「新增场景」创建第一个模板。
          </p>
        )}
        <p className="text-muted-foreground mt-6 text-xs">
          场景模板以 YAML 文件保存，刷新页面可加载最新内容。
        </p>
        <p
          role="status"
          className="mt-3 text-sm text-[#2F6868]"
        >
          {notice}
        </p>
      </div>
      <Dialog.Root
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open && !saving) setEditing(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
          <Dialog.Content
            className="bg-background fixed top-1/2 left-1/2 z-50 flex max-h-[92dvh] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border shadow-xl"
            onPointerDownOutside={(event) => event.preventDefault()}
          >
            <div className="border-b px-5 py-5 pr-14 sm:px-8">
              <Dialog.Title className="text-lg font-semibold">
                {editing?.index === -1 ? "新增场景" : "场景详情"}
              </Dialog.Title>
              <Dialog.Description className="text-muted-foreground mt-1 text-sm">
                直接编辑基本信息和分析思路，完成后保存。带 * 的字段为必填项。
              </Dialog.Description>
              <Dialog.Close asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={saving}
                  aria-label="关闭场景详情"
                  className="absolute top-4 right-4"
                >
                  <X />
                </Button>
              </Dialog.Close>
            </div>
            {editing && (
              <ScenarioEditor
                scenario={editing.scenario}
                onSave={save}
                onCancel={() => setEditing(null)}
              />
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<p role="status">正在加载场景…</p>}>
      <ScenariosPage />
    </Suspense>
  );
}
