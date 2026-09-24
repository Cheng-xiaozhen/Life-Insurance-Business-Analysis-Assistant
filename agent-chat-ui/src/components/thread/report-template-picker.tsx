"use client";

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { FileText, X } from "lucide-react";
import { z } from "zod";
import { Button } from "../ui/button";

const templatesSchema = z.array(
  z.object({ code: z.string().min(1), name: z.string().min(1) }),
);
export type ReportChoice = z.infer<typeof templatesSchema>[number];

export function ReportTemplatePicker({
  value,
  onChange,
  disabled,
}: {
  value: ReportChoice | null;
  onChange: (value: ReportChoice | null) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<ReportChoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setLoading(true);
    setError("");
    setTemplates([]);
    try {
      const response = await fetch("/api/report-templates", {
        cache: "no-store",
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "加载报告模板失败，请重试。");
      setTemplates(templatesSchema.parse(result.reports));
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "加载报告模板失败，请重试。",
      );
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="flex min-w-0 items-center gap-1">
      <Dialog.Root
        open={open && !disabled}
        onOpenChange={(next) => {
          setOpen(next);
          if (next) void load();
        }}
      >
        <Dialog.Trigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            className="max-w-full"
            aria-label={value ? `更换报告模板：${value.name}` : "选择报告模板"}
          >
            <FileText aria-hidden="true" />
            <span className="truncate">{value?.name ?? "选择报告模板"}</span>
          </Button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
          <Dialog.Content className="bg-background fixed top-1/2 left-1/2 z-50 flex max-h-[80dvh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border shadow-xl">
            <header className="border-b p-5 pr-14">
              <Dialog.Title className="font-semibold">
                选择报告模板
              </Dialog.Title>
              <Dialog.Description className="text-muted-foreground mt-2 text-sm">
                选择模板后，在对话框输入报告需求。
              </Dialog.Description>
              <Dialog.Close asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="关闭模板选择"
                  className="absolute top-3 right-3"
                >
                  <X />
                </Button>
              </Dialog.Close>
            </header>
            <div className="overflow-y-auto p-3">
              {loading && (
                <p
                  role="status"
                  className="text-muted-foreground p-3 text-sm"
                >
                  正在加载报告模板…
                </p>
              )}
              {error && (
                <div
                  role="alert"
                  className="space-y-3 p-3 text-sm"
                >
                  <p className="text-red-600">{error}</p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void load()}
                  >
                    重新加载
                  </Button>
                </div>
              )}
              {!loading && !error && !templates.length && (
                <p className="text-muted-foreground p-3 text-sm">
                  暂无报告模板，请先在报告模板管理页面新增。
                </p>
              )}
              <ul className="space-y-1">
                {templates.map((template) => (
                  <li key={template.code}>
                    <button
                      type="button"
                      aria-pressed={value?.code === template.code}
                      className="w-full rounded-lg px-3 py-3 text-left text-sm break-words hover:bg-teal-50 focus-visible:outline-2 focus-visible:outline-[#2F6868] aria-pressed:bg-teal-50 aria-pressed:text-[#2F6868]"
                      onClick={() => {
                        onChange(template);
                        setOpen(false);
                      }}
                    >
                      {template.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      {value && (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={disabled}
          aria-label="取消报告模板选择，返回智能问答"
          onClick={() => onChange(null)}
        >
          <X className="size-4" />
        </Button>
      )}
    </div>
  );
}
