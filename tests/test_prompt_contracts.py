"""离线：python -B tests/test_prompt_contracts.py

真实模型：追加 --live --output <结果.json>；可用 --baseline-dir <旧Prompt目录> 对比。
离线仅验证示例、消息及节点契约，不代表 LLM 语义质量通过。
"""

import argparse
import hashlib
import json
import re
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import ChartDecisions
from life_insurance_business_analysis_assistant.agent.nodes.resolve_slots import SlotExtraction
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt

ROOT = Path(__file__).resolve().parents[1]
NODES = ("resolve_slots", "analyze_step", "summarize_scenario", "recommend_charts")
MODULES = {name: import_module(
    f"life_insurance_business_analysis_assistant.agent.nodes.{name}"
) for name in NODES}


def run_case(case, model, prompt):
    """使用真实节点组装消息并执行校验；仅替换模型和系统提示词。"""
    name, payload = case["node"], case["input"]
    state = create_initial_state(payload.get("question", "契约验证"))
    state["scenario_id"] = "standard_premium_review"
    path = ROOT / "config/templates/Scenario"
    state.update(load_template(state, Runtime(context=AgentContext([], path))))
    template = state["template"]
    state["slots"] = deepcopy(payload.get("slots", {}))
    template.update(payload.get("scenario", {}))
    if name == "resolve_slots":
        template["slot_definitions"] = {
            key: {**definition, "required": True,
                  **({"minimum": 1, "maximum": 12} if key == "月份" else {})}
            for key, definition in payload["slot_definitions"].items()
        }
        state.update(slots=deepcopy(payload["existing_slots"]),
                     user_reply=payload["user_reply"], clarification=deepcopy(payload["clarification"]))
    elif name == "summarize_scenario":
        template["steps"] = [{"step_id": c["step_id"]} for c in payload["conclusions"]]
        state["step_index"] = len(template["steps"])
        state["step_results"] = [{**c, "data_uses": [], "conclusion_step_ids": []}
                                 for c in payload["conclusions"]]
    else:
        # 旧评估样本保留原始观测，适配新的数据引用契约；不补造缺失指标。
        data = deepcopy(payload.get("current_data", payload.get("data", payload.get("datasets", [{}])[0])))
        rows = data["rows"]
        metrics = payload["step"].get("metrics", case["output"].get("metrics", []) if isinstance(case["output"], dict) else [])
        if not metrics:
            metrics = [k for k, v in rows[0].items() if isinstance(v, (int, float))] if rows else []
        dimensions = [k for k in rows[0] if k not in metrics] if rows else []
        complete = all(all(row.get(m) is not None for m in metrics) for row in rows)
        requirement = {"requirement_id": "contract", "metrics": metrics, "dimensions": dimensions,
                       "grain": "contract", "scope": {}, "filters": [], "completeness": "available",
                       "time_ranges": {m: {"start": "2025-01-01", "end": "2025-12-31"} for m in metrics}}
        # 缺列样本只能以明确的未知值进入分析，不能冒充零值或完整数据。
        for row in rows:
            for metric in metrics:
                row.setdefault(metric, None)
        dataset = {"request_key": "contract", "source_id": "contract", "source_version": "1",
                   "population": "sample" if data.get("is_mock") else "business", "coverage": requirement,
                   "complete": complete, "truncated": False, "units": {m: None for m in metrics}, "data": data}
        use = {"requirement_id": "contract", "dataset_id": "contract", "metrics": metrics, "selection_filters": []}
        template["steps"] = [{**payload["step"], "metrics": metrics, "query_params": {}}]
        state["datasets"] = {"contract": dataset}
        if name == "analyze_step":
            state["step_plan"] = {"step_id": payload["step"]["step_id"], "requirements": [requirement],
                                  "data_uses": [use], "queries": [], "conclusion_step_ids": [],
                                  "clarification_answers": [], "reason": "离线契约样本"}
        else:
            template["analysis_purpose"] = payload["analysis_purpose"]
            state.update(step_index=1, summary="已完成总结", step_results=[{
                "step_id": payload["step"]["step_id"], "data_uses": [use], "conclusion_step_ids": [],
                "conclusion": payload["conclusion"],
            }])
    before = deepcopy(state)
    module = MODULES[name]
    with patch.object(module, "get_llm", return_value=model), \
         patch.object(module, "load_prompt", return_value=prompt):
        update = getattr(module, name)(state) if name == "resolve_slots" else getattr(module, name)(state, {})
    assert state == before, "节点不得原地修改状态"
    return update


def examples():
    for name in NODES:
        prompt = load_prompt(name)
        if name == "recommend_charts":
            assert "JSON Schema:" in prompt
            continue
        headings = re.findall(r"^## (\d{2}) (\w+)", prompt, re.M)
        assert headings == list(zip(
            [f"{i:02}" for i in range(1, 9)],
            ["Role", "Task", "Context", "Rules", "Workflow", "Output", "Edge", "Examples"],
        )), name
        blocks = re.findall(r"```json\n(.*?)\n```", prompt, re.S)
        assert blocks, name
        for index, block in enumerate(blocks):
            yield {"node": name, "id": f"example-{index + 1}", **json.loads(block)}


def structured_output(case):
    if case["node"] == "recommend_charts":
        return {"recommendations": [{**case["output"], "candidate_id": "data-1"}]}
    return case["output"]


def test_prompt_contracts():
    held_out = json.loads((ROOT / "tests/prompt_cases.json").read_text(encoding="utf-8"))
    cases = [*examples(), *held_out]
    for case in cases:
        name, expected = case["node"], case["output"]
        model = Mock()
        if name in ("resolve_slots", "recommend_charts"):
            schema = SlotExtraction if name == "resolve_slots" else ChartDecisions
            schema.model_validate(structured_output(case))
            model.with_structured_output.return_value.invoke.return_value = structured_output(case)
        else:
            assert isinstance(expected, str) and expected.strip()
            model.stream_events.return_value = Mock(text=iter([expected]), output=AIMessage(content=expected))
        update = run_case(case, model, load_prompt(name))
        if name in ("resolve_slots", "recommend_charts"):
            method = "function_calling" if name == "resolve_slots" else "json_mode"
            model.with_structured_output.assert_called_once_with(schema, method=method)
            messages = model.with_structured_output.return_value.invoke.call_args.args[0]
        else:
            messages = model.stream_events.call_args.args[0]
            actual = update["summary"] if name == "summarize_scenario" else update["step_results"][-1]["conclusion"]
            assert actual == expected
        assert [m[0] for m in messages] == ["system", "human"]
        actual_input = json.loads(messages[1][1])
        if name in ("resolve_slots", "summarize_scenario"):
            assert actual_input == case["input"], case["id"]
        elif name == "analyze_step":
            assert actual_input["step"] == case["input"]["step"]
            assert actual_input["datasets"][0]["rows"] == case["input"].get("current_data", case["input"].get("datasets", [{}])[0])["rows"]
            assert actual_input["conclusions"] == []
        else:
            assert actual_input["candidates"][0]["step_id"] == case["input"]["step"]["step_id"]
            assert actual_input["candidates"][0]["conclusion"] == case["input"]["conclusion"]
        if name == "recommend_charts":
            system, schema_text = messages[0][1].split("JSON Schema:\n")
            assert json.loads(schema_text) == ChartDecisions.model_json_schema()
            actual = update["chart_recommendations"][0]
            assert actual["step_id"] == expected["step_id"]
            if not expected["recommended"]:
                assert not actual["recommended"]
            # 图表推荐另经 Python 安全校验；未声明时间轴的旧样本不应画折线。
            if actual["recommended"]:
                assert actual["chart_type"] == expected["chart_type"]
                assert actual["data"]
        else:
            assert messages[0][1] == load_prompt(name)
        if "expected_slots" in case:
            assert update["slots"] == case["expected_slots"], case["id"]
            actual_issues = {i["slot_name"]: i["reason"] for i in
                             (update["clarification"] or {}).get("slot_issues", [])}
            assert actual_issues == case["expected_issues"], case["id"]
    print(f"Prompt examples / held-out message and node contracts: PASS ({len(cases)} cases)")


def live(args):
    """只跑未出现在 Few-shot 中的样本；正文人工复核，不用关键词充当语义评分。"""
    cases = json.loads((ROOT / "tests/prompt_cases.json").read_text(encoding="utf-8"))
    versions = [("optimized", None)]
    if args.baseline_dir:
        versions.insert(0, ("baseline", Path(args.baseline_dir)))
    results = []
    for version, directory in versions:
        for case in cases:
            name = case["node"]
            record = {"version": version, "id": case["id"], "node": name,
                      "input": case["input"], "expected": case["output"],
                      "review": case["review"]}
            try:
                model = get_llm(thinking=name != "resolve_slots")
                if model is None:
                    raise RuntimeError("模型未配置")
                client = model.root_client.with_options(timeout=30, max_retries=0)
                model = model.model_copy(update={"root_client": client, "client": client.chat.completions})
                prompt = (directory / f"{name}.md").read_text(encoding="utf-8") if directory else load_prompt(name)
                record.update(model=model.model_name,
                              prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest())
                if name in ("resolve_slots", "recommend_charts"):
                    # 保留合并前的增量，避免旧值被重新抽取却被最终状态掩盖。
                    structured = model.with_structured_output

                    def capture(schema, **kwargs):
                        runnable = structured(schema, **kwargs)

                        def invoke(*args, **kwargs):
                            raw = runnable.invoke(*args, **kwargs)
                            record["raw_output"] = raw.model_dump() if hasattr(raw, "model_dump") else raw
                            return raw

                        return Mock(invoke=invoke)

                    model = Mock(wraps=model)
                    model.with_structured_output.side_effect = capture
                record["update"] = run_case(case, model, prompt)
                record["status"] = "contract_passed_semantics_need_review"
            except Exception as error:
                # 不写异常全文，避免服务地址或认证信息进入可提交的报告。
                record.update(status="error", error=type(error).__name__)
                results.append(record)
                args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                raise SystemExit(f"Live evaluation stopped: {type(error).__name__}; saved {args.output}")
            results.append(record)
            args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(version, case["id"], record["status"], flush=True)


def test_live_recording():
    """验证评估记录链路；仍然使用 Mock，不访问模型服务。"""
    cases = json.loads((ROOT / "tests/prompt_cases.json").read_text(encoding="utf-8"))
    models = []
    for case in cases:
        model = Mock(model_name="offline-test")
        model.model_copy.return_value = model
        model.with_structured_output.return_value.invoke.return_value = structured_output(case)
        if isinstance(case["output"], str):
            model.stream_events.return_value = Mock(
                text=iter([case["output"]]), output=AIMessage(content=case["output"]),
            )
        models.append(model)
    with TemporaryDirectory() as directory, patch(__name__ + ".get_llm", side_effect=models):
        output = Path(directory) / "results.json"
        live(SimpleNamespace(baseline_dir=None, output=output))
        records = json.loads(output.read_text(encoding="utf-8"))
        assert len(records) == len(cases)
        for record, case, model in zip(records, cases, models, strict=True):
            model.root_client.with_options.assert_called_once_with(timeout=30, max_retries=0)
            assert len(record["prompt_sha256"]) == 64
            if case["node"] in ("resolve_slots", "recommend_charts"):
                assert record["raw_output"] == structured_output(case)
    print("Evaluation recording (Mock only): PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--baseline-dir")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live:
        if args.output is None:
            parser.error("--live requires --output")
        live(args)
    else:
        test_prompt_contracts()
        test_live_recording()
