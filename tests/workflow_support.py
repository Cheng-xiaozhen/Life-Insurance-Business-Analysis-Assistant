"""离线工作流检查共用的模拟模型；绝不作为运行时回退。"""

import json
import re
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.data_query import DataQueryResult

TEMPLATE = Path(__file__).resolve().parents[1] / "config/templates/Scenario"
SLOTS = {"年份": 2026, "月份": 8}


def query_fixture(request):
    """仅供离线测试的固定观测；运行时不会使用。"""
    detail = "机构" in request.step.text and "全系统" not in request.step.text
    dimensions = ["机构"] if detail else []
    rows = [{**({"机构": name} if detail else {}), **{m: value for m in request.metrics}}
            for name, value in ([("甲", 80.0), ("乙", 40.0)] if detail else [("总体", 100.0)])]
    return DataQueryResult.model_validate({"datasets": [{
        "dimensions": dimensions, "metrics": request.metrics, "rows": rows,
        "units": {m: "%" if any(word in m for word in ("率", "进度", "同比")) else "万元" for m in request.metrics},
        "is_mock": True, "complete": True, "notice": "离线独立模拟样例，未指定年月，不代表真实全系统。",
    }]})


def context(path=TEMPLATE):
    return AgentContext(load_scenario_catalog(path), path, Mock(side_effect=query_fixture))


def payload(messages):
    return json.loads(messages[1][1])


def models():
    result = {name: Mock() for name in ("match_scenario", "resolve_slots", "analyze_step", "summarize_scenario", "recommend_charts")}
    def match(messages, **kwargs):
        data = payload(messages)
        return {"candidates": [{"scenario_id": entry["scenario_id"], "confidence": 0.9, "reason": "离线模拟匹配"}
                               for entry in data["catalog"] if any(word in data["question"] for word in entry["keywords"])]}
    def slots(messages, **kwargs):
        data = payload(messages)
        text = data["user_reply"] or data["question"]
        values = {}
        for name, pattern in (("年份", r"(\d{4})年"), ("月份", r"(\d{1,2})月")):
            found = re.search(pattern, text)
            if found:
                values[name] = int(found[1])
        for name, value in (("渠道", "个险"), ("机构范围", "全系统")):
            if name in data["slot_definitions"] and value in text:
                values[name] = value
        return {"values": values, "ambiguous": {}}
    def analyze(messages, **kwargs):
        return FakeListChatModel(responses=[f"模拟步骤结论-{payload(messages)['step']['step_id']}"]).stream_events(messages, **kwargs)
    def charts(messages, **kwargs):
        candidates = payload(messages)["candidates"]
        candidate = next((c for c in candidates if c["dimensions"] and len(c["data"]["rows"]) > 1), candidates[0])
        recommended = bool(candidate["dimensions"]) and len(candidate["data"]["rows"]) > 1
        return {"recommendations": [{"recommended": recommended, "chart_type": "bar" if recommended else None,
                                    "step_id": candidate["step_id"], "candidate_id": candidate["candidate_id"],
                                    "dimensions": candidate["dimensions"] if recommended else [],
                                    "metrics": candidate["metrics"][:1] if recommended else [],
                                    "reason": "模拟图表决策", "description": "仅用于离线验证"}]}
    for name, handler in (("match_scenario", match), ("resolve_slots", slots), ("recommend_charts", charts)):
        result[name].with_structured_output.return_value.invoke.side_effect = handler
    result["analyze_step"].stream_events.side_effect = analyze
    result["summarize_scenario"].stream_events.side_effect = lambda messages, **kwargs: FakeListChatModel(responses=["模拟场景总结"]).stream_events(messages, **kwargs)
    return result


@contextmanager
def patched_models(items):
    with ExitStack() as stack:
        for name, model in items.items():
            stack.enter_context(patch(f"life_insurance_business_analysis_assistant.agent.nodes.{name}.get_llm", return_value=model))
        yield
