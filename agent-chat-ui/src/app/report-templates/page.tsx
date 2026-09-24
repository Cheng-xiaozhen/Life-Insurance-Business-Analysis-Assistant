"use client";

import { Suspense, useEffect, useId, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, ArrowUp, ArrowDown, Plus, X } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { TagInput } from "@/components/ui/tag-input";

const analysisSchema = z.object({
  id: z.string(),
  text: z.string().trim().min(1),
  metrics: z.array(z.string()),
  mode: z.string(),
});
const chapterSchema = analysisSchema.extend({
  name: z.string().trim().min(1),
  children: z.array(
    z.object({
      id: z.string(),
      name: z.string().trim().min(1),
      steps: z.array(analysisSchema).min(1),
    }),
  ),
});
const reportSchema = z.object({
  code: z.string().trim().min(1),
  name: z.string().trim().min(1),
  channel: z.string(),
  period: z.string(),
  target: z.string(),
  purpose: z.string(),
  chapters: z.array(chapterSchema).min(1),
  tone: z.string(),
  conclusion: z.string(),
  units: z.string(),
  examples: z.array(z.string()),
});
type Report = z.infer<typeof reportSchema>;
type Analysis = z.infer<typeof analysisSchema>;
const basicFields = [
  ["code", "报告编码"],
  ["name", "报告名称"],
  ["channel", "渠道类型"],
  ["period", "时间维度"],
  ["target", "分析对象"],
  ["purpose", "分析目的"],
] as const;
const styleFields = [
  ["tone", "语气风格"],
  ["conclusion", "结论风格"],
  ["units", "单位规则"],
] as const;
const newAnalysis = (): Analysis => ({
  id: crypto.randomUUID(),
  text: "",
  metrics: [],
  mode: "",
});
const blank = (): Report => ({
  code: "",
  name: "",
  channel: "",
  period: "",
  target: "",
  purpose: "",
  chapters: [{ ...newAnalysis(), name: "", children: [] }],
  tone: "",
  conclusion: "",
  units: "",
  examples: [],
});

function TextField({
  label,
  value,
  onChange,
  multiline = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
}) {
  const id = useId();
  const Control = multiline ? Textarea : Input;
  return (
    <div className="grid gap-2 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      <Control
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function AnalysisFields({
  analysis,
  onChange,
  chapter = false,
}: {
  analysis: Analysis;
  onChange: (value: Analysis) => void;
  chapter?: boolean;
}) {
  return (
    <div className="grid gap-4">
      <TextField
        label="分析步骤 *"
        value={analysis.text}
        multiline
        onChange={(text) => onChange({ ...analysis, text })}
      />
      <TagInput
        name={`metrics-${analysis.id}`}
        label="关联指标"
        defaultValue={analysis.metrics}
      />
      <TextField
        label="分析模式"
        value={analysis.mode}
        onChange={(mode) => onChange({ ...analysis, mode })}
      />
    </div>
  );
}

function OrderButtons({
  label,
  index,
  total,
  move,
  remove,
  minimum = 0,
}: {
  label: string;
  index: number;
  total: number;
  move: (offset: number) => void;
  remove: () => void;
  minimum?: number;
}) {
  return (
    <div className="flex justify-end gap-1">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`上移${label}`}
        disabled={index === 0}
        onClick={() => move(-1)}
      >
        <ArrowUp />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`下移${label}`}
        disabled={index === total - 1}
        onClick={() => move(1)}
      >
        <ArrowDown />
      </Button>
      <Button
        type="button"
        variant="ghost"
        disabled={total <= minimum}
        onClick={remove}
      >
        删除{label}
      </Button>
    </div>
  );
}
function reordered<T>(items: T[], index: number, offset: number) {
  const next = [...items];
  [next[index], next[index + offset]] = [next[index + offset], next[index]];
  return next;
}

function Editor({
  report,
  onSave,
  onClose,
  saving,
}: {
  saving: boolean;
  report: Report;
  onSave: (report: Report) => Promise<string | undefined>;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(() => structuredClone(report));
  const [error, setError] = useState("");
  const updateChapter = (index: number, chapter: Report["chapters"][number]) =>
    setDraft((current) => ({
      ...current,
      chapters: current.chapters.map((value, i) =>
        i === index ? chapter : value,
      ),
    }));
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const metrics = (analysis: Analysis) => ({
      ...analysis,
      metrics: [
        ...new Set(
          form
            .getAll(`metrics-${analysis.id}`)
            .flatMap((value) => String(value).split(/[\n,，;；]+/))
            .map((value) => value.trim())
            .filter(Boolean),
        ),
      ],
    });
    const parsed = reportSchema.safeParse({
      ...draft,
      examples: draft.examples.map((value) => value.trim()).filter(Boolean),
      chapters: draft.chapters.map((chapter) => ({
        ...chapter,
        ...metrics(chapter),
        children: chapter.children.map((child) => ({
          ...child,
          steps: child.steps.map(metrics),
        })),
      })),
    });
    if (!parsed.success) {
      setError(
        "请填写报告编码、报告名称、所有章节与子章节名称，以及每个章节和子章节的分析步骤；至少保留一个章节。",
      );
      return;
    }
    setError((await onSave(parsed.data)) ?? "");
  }
  function close() {
    if (window.confirm("放弃本次编辑并关闭？")) onClose();
  }
  return (
    <form
      onSubmit={save}
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-10">
        <fieldset
          disabled={saving}
          className="mx-auto max-w-4xl min-w-0 space-y-8"
        >
          <section>
            <h2 className="mb-5 text-lg font-semibold">基本信息</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {basicFields.map(([key, label]) => (
                <TextField
                  key={key}
                  label={`${label}${key === "code" || key === "name" ? " *" : ""}`}
                  value={draft[key]}
                  onChange={(value) => setDraft({ ...draft, [key]: value })}
                  multiline={key === "purpose"}
                />
              ))}
            </div>
          </section>
          <section className="border-t pt-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                章节板块 · {draft.chapters.length}
              </h2>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  setDraft({
                    ...draft,
                    chapters: [
                      ...draft.chapters,
                      { ...newAnalysis(), name: "", children: [] },
                    ],
                  })
                }
              >
                <Plus />
                添加章节
              </Button>
            </div>
            <div className="space-y-4">
              {draft.chapters.map((chapter, ci) => (
                <details
                  key={chapter.id}
                  open
                  className="rounded-xl border bg-slate-50/60"
                >
                  <summary className="cursor-pointer px-5 py-4 font-semibold">
                    {ci + 1}. {chapter.name || "未命名章节"}
                    <span className="text-muted-foreground ml-3 text-xs font-normal">
                      {chapter.children.length} 个子章节
                    </span>
                  </summary>
                  <div className="space-y-5 border-t p-5">
                    <OrderButtons
                      label={`章节 ${ci + 1}`}
                      index={ci}
                      total={draft.chapters.length}
                      minimum={1}
                      move={(offset) =>
                        setDraft({
                          ...draft,
                          chapters: reordered(draft.chapters, ci, offset),
                        })
                      }
                      remove={() =>
                        setDraft({
                          ...draft,
                          chapters: draft.chapters.filter((_, i) => i !== ci),
                        })
                      }
                    />
                    <TextField
                      label="板块名称 *"
                      value={chapter.name}
                      onChange={(name) =>
                        updateChapter(ci, { ...chapter, name })
                      }
                    />
                    <AnalysisFields
                      chapter
                      analysis={chapter}
                      onChange={(value) =>
                        updateChapter(ci, { ...chapter, ...value })
                      }
                    />
                    <div className="flex items-center justify-between border-t pt-4">
                      <h3 className="font-medium">子章节板块</h3>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() =>
                          updateChapter(ci, {
                            ...chapter,
                            children: [
                              ...chapter.children,
                              {
                                id: crypto.randomUUID(),
                                name: "",
                                steps: [newAnalysis()],
                              },
                            ],
                          })
                        }
                      >
                        <Plus />
                        添加子章节
                      </Button>
                    </div>
                    {!chapter.children.length && (
                      <p className="text-muted-foreground text-sm">
                        暂无子章节，可按需添加。
                      </p>
                    )}
                    {chapter.children.map((child, si) => {
                      const updateChild = (value: typeof child) =>
                        updateChapter(ci, {
                          ...chapter,
                          children: chapter.children.map((item, i) =>
                            i === si ? value : item,
                          ),
                        });
                      return (
                        <details
                          key={child.id}
                          open
                          className="bg-background rounded-lg border"
                        >
                          <summary className="cursor-pointer px-4 py-3 font-medium">
                            {ci + 1}.{si + 1} {child.name || "未命名子章节"}
                          </summary>
                          <div className="space-y-4 border-t p-4">
                            <OrderButtons
                              label={`子章节 ${si + 1}`}
                              index={si}
                              total={chapter.children.length}
                              move={(offset) =>
                                updateChapter(ci, {
                                  ...chapter,
                                  children: reordered(
                                    chapter.children,
                                    si,
                                    offset,
                                  ),
                                })
                              }
                              remove={() =>
                                updateChapter(ci, {
                                  ...chapter,
                                  children: chapter.children.filter(
                                    (_, i) => i !== si,
                                  ),
                                })
                              }
                            />
                            <TextField
                              label="子章节板块名 *"
                              value={child.name}
                              onChange={(name) =>
                                updateChild({ ...child, name })
                              }
                            />
                            <h4 className="text-sm font-semibold">分析思路</h4>
                            {child.steps.map((step, ti) => (
                              <fieldset
                                key={step.id}
                                className="min-w-0 rounded-lg border p-4"
                              >
                                <legend className="px-2 text-sm font-semibold">
                                  步骤 {ti + 1}
                                </legend>
                                <OrderButtons
                                  label={`步骤 ${ti + 1}`}
                                  index={ti}
                                  total={child.steps.length}
                                  minimum={1}
                                  move={(offset) =>
                                    updateChild({
                                      ...child,
                                      steps: reordered(child.steps, ti, offset),
                                    })
                                  }
                                  remove={() =>
                                    updateChild({
                                      ...child,
                                      steps: child.steps.filter(
                                        (_, i) => i !== ti,
                                      ),
                                    })
                                  }
                                />
                                <AnalysisFields
                                  analysis={step}
                                  onChange={(value) =>
                                    updateChild({
                                      ...child,
                                      steps: child.steps.map((item, i) =>
                                        i === ti ? value : item,
                                      ),
                                    })
                                  }
                                />
                              </fieldset>
                            ))}
                            <Button
                              type="button"
                              variant="outline"
                              onClick={() =>
                                updateChild({
                                  ...child,
                                  steps: [...child.steps, newAnalysis()],
                                })
                              }
                            >
                              <Plus />
                              添加步骤
                            </Button>
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </details>
              ))}
            </div>
          </section>
          <section className="space-y-4 border-t pt-6">
            <h2 className="text-lg font-semibold">写作风格与格式要求</h2>
            {styleFields.map(([key, label]) => (
              <TextField
                key={key}
                label={label}
                value={draft[key]}
                multiline
                onChange={(value) => setDraft({ ...draft, [key]: value })}
              />
            ))}
            <TextField
              label="句式示例（每行一条）"
              value={draft.examples.join("\n")}
              multiline
              onChange={(value) =>
                setDraft({ ...draft, examples: value.split("\n") })
              }
            />
          </section>
        </fieldset>
      </div>
      <footer className="flex flex-wrap items-center justify-end gap-3 border-t px-5 py-4 sm:px-10">
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
          onClick={close}
          disabled={saving}
        >
          取消
        </Button>
        <Button
          type="submit"
          disabled={saving}
          variant="brand"
        >
          {saving ? "保存中…" : "保存模板"}
        </Button>
      </footer>
    </form>
  );
}

function ReportsPage() {
  const params = useSearchParams();
  const [reports, setReports] = useState<Report[]>([]);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<{
    index: number;
    report: Report;
  } | null>(null);
  async function load() {
    try {
      const response = await fetch("/api/report-templates", {
        cache: "no-store",
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      setReports(z.array(reportSchema).parse(result.reports));
      setError("");
      setReady(true);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "加载报告模板失败，请重试。",
      );
    }
  }
  useEffect(() => {
    void load();
  }, []);
  function close() {
    if (!saving && window.confirm("放弃本次编辑并关闭？")) setEditing(null);
  }
  async function save(report: Report): Promise<string | undefined> {
    if (!editing || saving) return;
    setSaving(true);
    try {
      const response = await fetch("/api/report-templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report,
          originalCode: editing.index === -1 ? null : editing.report.code,
        }),
      });
      const result = await response.json();
      if (!response.ok) return result.error ?? "保存报告模板失败，请重试。";
      const saved = reportSchema.parse(result.report);
      setReports((current) =>
        editing.index === -1
          ? [...current, saved]
          : current.map((value, index) =>
              index === editing.index ? saved : value,
            ),
      );
      setEditing(null);
      setNotice(`已保存「${saved.name}」。`);
    } catch {
      return "保存失败，请检查服务连接后重试。编辑内容已保留。";
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
          <Link href={params.size ? `/?${params}` : "/"}>
            <ArrowLeft />
            返回分析对话
          </Link>
        </Button>
      </header>
      <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="mb-10 flex flex-wrap items-start justify-between gap-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              报告模板管理
            </h1>
            <p className="text-muted-foreground mt-3 text-sm">
              管理报告结构、分析思路与写作要求。
            </p>
          </div>
          <Button
            variant="brand"
            disabled={!ready}
            onClick={() => setEditing({ index: -1, report: blank() })}
          >
            <Plus />
            新增报告模板
          </Button>
        </div>
        <h2 className="mb-4 font-medium">全部模板 · {reports.length}</h2>
        {error && (
          <p
            role="alert"
            className="mb-4 text-red-600"
          >
            {error}
            <Button
              variant="outline"
              onClick={() => void load()}
              className="ml-3"
            >
              重新加载
            </Button>
          </p>
        )}
        {!ready && !error && <p role="status">正在加载模板…</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          {reports.map((report, index) => (
            <button
              key={report.code}
              onClick={() => setEditing({ index, report })}
              className="bg-background grid gap-3 rounded-xl border p-6 text-left transition-colors hover:border-[#2F6868] hover:bg-teal-50/40 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#2F6868]"
            >
              <span className="font-semibold break-all">{report.name}</span>
              <span className="text-muted-foreground text-xs break-all">
                {report.code}
              </span>
              <span className="text-muted-foreground text-sm">
                {report.channel || "未设置渠道"} ·{" "}
                {report.period || "未设置时间维度"} · {report.chapters.length}{" "}
                个章节
              </span>
            </button>
          ))}
        </div>
        {ready && !reports.length && (
          <p className="text-muted-foreground rounded-xl border border-dashed p-10 text-center">
            暂无模板，点击「新增报告模板」开始创建。
          </p>
        )}
        <p className="text-muted-foreground mt-6 text-xs">
          报告模板以 YAML 文件保存在
          config/templates/Report，文件名使用报告编码。
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
          if (!open) close();
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
          <Dialog.Content
            className="bg-background fixed inset-0 z-50 flex h-dvh flex-col"
            onPointerDownOutside={(event) => event.preventDefault()}
          >
            <header className="relative border-b px-5 py-5 pr-16 sm:px-10">
              <Dialog.Title className="text-lg font-semibold">
                {editing?.index === -1 ? "新增报告模板" : "报告模板详情"}
              </Dialog.Title>
              <Dialog.Description className="text-muted-foreground mt-1 text-sm">
                查看或编辑模板。章节可折叠，步骤按排列顺序自动编号，带 *
                的字段必填。
              </Dialog.Description>
              <Dialog.Close asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={saving}
                  aria-label="关闭报告模板"
                  className="absolute top-4 right-4"
                >
                  <X />
                </Button>
              </Dialog.Close>
            </header>
            {editing && (
              <Editor
                report={editing.report}
                saving={saving}
                onSave={save}
                onClose={() => setEditing(null)}
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
    <Suspense fallback={<p role="status">正在加载模板…</p>}>
      <ReportsPage />
    </Suspense>
  );
}
