import { useRef, useState } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import { Download, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { getAnalysisReport } from "@/lib/analysis-report";

export function ReportDownload({
  messages,
  analysisId,
}: {
  messages: Message[];
  analysisId: string;
}) {
  const [busy, setBusy] = useState(false);
  const downloading = useRef(false);
  const report = getAnalysisReport(messages, analysisId);
  if (!report) return null;
  const download = async () => {
    if (downloading.current) return;
    downloading.current = true;
    setBusy(true);
    try {
      const { createReportDocx } = await import("@/lib/report-docx");
      const blob = await createReportDocx(report);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const name = Array.from(report.question.replace(/[<>:"/\\|?*]/g, "_"))
        .map((character) => (character.charCodeAt(0) < 32 ? "_" : character))
        .slice(0, 60)
        .join("")
        .replace(/[. ]+$/, "");
      anchor.download = `${name || report.title}_分析报告.docx`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      toast.error("报告下载失败，请重试。");
    } finally {
      downloading.current = false;
      setBusy(false);
    }
  };
  return (
    <Button
      variant="outline"
      disabled={busy}
      onClick={() => void download()}
      className="self-start"
    >
      {busy ? (
        <LoaderCircle
          aria-hidden="true"
          className="size-4 animate-spin"
        />
      ) : (
        <Download
          aria-hidden="true"
          className="size-4"
        />
      )}
      {busy ? "正在生成 Word…" : "下载报告"}
    </Button>
  );
}
