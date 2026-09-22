"""python -B tests/test_recommend_charts.py；候选来源、真实数值组装和拒绝无效图表。"""

from copy import deepcopy
from unittest.mock import patch

from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import (
    ChartDecision, ChartDecisions, assemble_chart, chart_candidates, recommend_charts,
)
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from workflow_support import context, models, patched_models, payload


def test_recommend_charts():
    ctx, mock = context(), models()
    graph = build_graph()
    config = {"configurable": {"thread_id": "charts"}, "recursion_limit": 100}
    with patched_models(mock):
        graph.invoke(create_initial_state("2026年8月个险全系统标保"), config, context=ctx)
        state = graph.invoke(Command(resume="standard_premium_review"), config, context=ctx)
    candidates = chart_candidates(state)
    assert len(candidates) == 3  # 第2/3、第4/5步的重复数据候选去重。
    candidate = next(c for c in candidates if c["step_id"] == 2)
    decision = ChartDecision(recommended=True, chart_type="bar", step_id=2, candidate_id=candidate["candidate_id"],
                             dimensions=["机构"], metrics=["标保达成率"], reason="比较模拟机构", description="使用样例数据")
    before = deepcopy(state)
    assembled = assemble_chart(decision, candidate)
    assert assembled["recommended"] and assembled["units"] == {"标保达成率": "%"}
    assert assembled["data"][0]["标保达成率"] == float(candidate["data"]["rows"][0]["标保达成率"].removesuffix("%"))
    assert "模拟" in assembled["description"]
    for changes in ({"chart_type": "pie"}, {"chart_type": "line"}, {"chart_type": "scatter"}, {"dimensions": []}):
        result = assemble_chart(decision.model_copy(update=changes), candidate)
        assert not result["recommended"] and not result["data"]
    for changes in ({"metrics": ["不存在"]}, {"dimensions": ["标保达成率"]}, {"step_id": 1}):
        try:
            assemble_chart(decision.model_copy(update=changes), candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("未知引用必须拒绝")
    invoke = mock["recommend_charts"].with_structured_output.return_value.invoke
    invoke.side_effect = None
    invoke.return_value = {"recommendations": [decision.model_dump()]}
    with patched_models(mock):
        update = recommend_charts(state, {})
        assert update["chart_recommendations"][0] == assembled
        assert state == before
        sent = payload(invoke.call_args.args[0])
        assert any(c["step_id"] == 4 for c in sent["candidates"])
        invoke.side_effect = RuntimeError("模型失败")
        try:
            recommend_charts(state, {})
        except RuntimeError:
            pass
        else:
            raise AssertionError("模型失败不能伪装为不推荐")
    assert state == before
    print("chart candidate deduplication, numeric assembly and validation: PASS")


if __name__ == "__main__":
    test_recommend_charts()
