import { execFile } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const root = path.resolve(process.cwd(), "..");
const directory =
  process.env.SCENARIO_TEMPLATE_DIR ??
  path.join(root, "config/templates/Scenario");
const python =
  process.env.SCENARIO_PYTHON ??
  path.join(
    root,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );

async function run(payload: object) {
  try {
    const output = await new Promise<string>((resolve, reject) => {
      const child = execFile(
        python,
        [
          "-X",
          "utf8",
          path.join(
            root,
            "src/life_insurance_business_analysis_assistant/scenario_store.py",
          ),
          directory,
        ],
        {
          cwd: root,
          timeout: 15000,
          maxBuffer: 4 * 1024 * 1024,
          windowsHide: true,
        },
        (error, stdout) => (error ? reject(error) : resolve(stdout)),
      );
      child.stdin?.on("error", reject);
      child.stdin?.end(JSON.stringify(payload));
    });
    const result = JSON.parse(output);
    return Response.json(result, { status: result.status ?? 200 });
  } catch {
    return Response.json(
      { error: "场景文件服务不可用，请检查 Python 环境后重试。" },
      { status: 500 },
    );
  }
}

export async function GET() {
  return run({ action: "list" });
}

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (
    (origin && origin !== new URL(request.url).origin) ||
    request.headers.get("sec-fetch-site") === "cross-site"
  ) {
    return Response.json({ error: "不允许跨站保存场景。" }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return Response.json({ error: "请求必须为 JSON。" }, { status: 415 });
  }
  try {
    const body = await request.text();
    if (Buffer.byteLength(body) > 1024 * 1024)
      return Response.json({ error: "模板内容超过 1 MB。" }, { status: 413 });
    const payload = JSON.parse(body);
    return run({
      action: "save",
      scenario: payload.scenario,
      originalCode: payload.originalCode,
    });
  } catch {
    return Response.json({ error: "请求内容无效。" }, { status: 400 });
  }
}
