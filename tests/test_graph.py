"""python -B tests/test_graph.py；场景确认、槽位/步骤澄清与独立线程恢复。"""

from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from workflow_support import context, models, patched_models


def test_graph():
    ctx, mock = context(), models()
    graph = build_graph()
    configs = [{"configurable": {"thread_id": name}, "recursion_limit": 100} for name in ("a", "b")]
    with patched_models(mock):
        for config in configs:
            result = graph.invoke(create_initial_state("2026年8月个险全系统标保和价值"), config, context=ctx)
            assert result["__interrupt__"][0].value["kind"] == "scenario_selection"
            assert result["scenario_id"] is None and result["template"] is None
        for invalid in ("", "unknown", 1, ["value_review"]):
            result = graph.invoke(Command(resume=invalid), configs[0], context=ctx)
            assert "选择无效" in result["__interrupt__"][0].value["prompt"]
        result = graph.invoke(Command(resume="value_review"), configs[0], context=ctx)
        assert result["scenario_id"] == "value_review" and result["summary"]
        assert graph.get_state(configs[1]).next == ("clarify",)
        planner = mock["plan_step"].with_structured_output.return_value.invoke
        original = planner.side_effect
        called = False
        def plan(messages, **kwargs):
            nonlocal called
            if not called:
                called = True
                return {"requirements": [], "conclusion_step_ids": [], "clarification": "请确认当前步骤分析对象", "reason": "测试步骤澄清"}
            return original(messages, **kwargs)
        planner.side_effect = plan
        result = graph.invoke(Command(resume="standard_premium_review"), configs[1], context=ctx)
        interrupt = result["__interrupt__"][0]
        assert interrupt.value["kind"] == "step_clarification"
        before = ctx.query_data.call_count
        result = graph.invoke(Command(resume={interrupt.id: "按模板全系统分析"}), configs[1], context=ctx)
        assert result["summary"] and ctx.query_data.call_count == before + 3
        assert mock["match_scenario"].with_structured_output.return_value.invoke.call_count == 2
        assert mock["resolve_slots"].with_structured_output.return_value.invoke.call_count == 2
    print("graph confirmation, step clarification, thread isolation: PASS")


if __name__ == "__main__":
    test_graph()
