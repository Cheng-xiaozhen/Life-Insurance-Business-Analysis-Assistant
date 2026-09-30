"""python -B tests/test_graph.py；场景确认、确定性路由与独立线程恢复。"""

from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.graph import build_analysis_graph
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import create_initial_state
from workflow_support import context, models, patched_models


def test_graph():
    ctx, mock = context(), models()
    graph = build_analysis_graph()
    assert "analysis_execution" in graph.builder.nodes
    assert not {"fetch_step_data", "analyze_step", "load_step"} & graph.builder.nodes.keys()
    assert ("load_template", "analysis_execution") in graph.builder.edges
    assert ("analysis_execution", "summarize_scenario") in graph.builder.edges
    assert ("summarize_scenario", "recommend_charts") in graph.builder.edges
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
        result = graph.invoke(Command(resume="standard_premium_review"), configs[1], context=ctx)
        assert result["summary"] and ctx.query_data.call_count == 8
        assert mock["match_scenario"].with_structured_output.return_value.invoke.call_count == 2
    print("graph confirmation, deterministic routing, thread isolation: PASS")


if __name__ == "__main__":
    test_graph()
