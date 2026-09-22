"""运行：python -B tests/test_analyze_step.py；验证 v3 消息流，不访问模型服务。"""

from copy import deepcopy
from workflow_support import context, models, patched_models
from life_insurance_business_analysis_assistant.agent.nodes.plan_step import plan_step
from life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data import fetch_step_data
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessageChunk
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.nodes.analyze_step import analyze_step
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state


@patch("life_insurance_business_analysis_assistant.agent.nodes.analyze_step.get_llm")
def test_analyze_step(get_llm):
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario"
    state = create_initial_state("2026年8月个险全系统标保")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=AgentContext([], path))))
    state["step_index"] = 1
    state["slots"] = {"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}
    state["step_results"] = [{"step_id": 1, "data_uses": [], "conclusion_step_ids": [], "conclusion": "前序结论"}]
    runtime = Runtime(context=context())
    with patched_models(models()):
        state.update(plan_step(state, runtime))
    state.update(fetch_step_data(state, runtime))
    before = deepcopy(state)
    model = Mock()
    model.stream_events.return_value = Mock(text=iter(["模拟数据：", "甲达成率80%。"]), output=AIMessageChunk(content="模拟数据：甲达成率80%。"))
    get_llm.return_value = model
    update = analyze_step(state, {})
    prompt = model.stream_events.call_args.args[0][1][1]
    assert "前序数据" not in prompt and "前序结论" not in prompt
    assert state["question"] in prompt and "全年标保" not in prompt
    assert state == before
    assert update["step_results"][-1]["conclusion"] == "模拟数据：甲达成率80%。"
    assert update["step_results"][0] == before["step_results"][0]
    assert update["step_index"] == 2 and update["step_plan"] is None
    update["step_results"][-1]["data_uses"].clear()
    assert state == before

    def failing_stream():
        yield AIMessageChunk(content="未完成")
        raise RuntimeError("模型中断")
    for case, chunks in enumerate((iter([AIMessageChunk(content=" ")]), failing_stream(),
                   iter([AIMessageChunk(content="截断", response_metadata={"finish_reason": "length"})]))):
        model.stream_events.return_value = Mock(text=(str(c.text) for c in chunks), output=AIMessageChunk(content="", response_metadata={"finish_reason": "length"} if case == 2 else {}))
        try:
            analyze_step(state, {})
        except RuntimeError:
            pass
        else:
            raise AssertionError("不完整结论不应提交")
        assert state == before

    get_llm.return_value = FakeListChatModel(responses=["模拟数据：甲达成率80%。"])
    graph = StateGraph(AgentState)
    graph.add_node("analyze_step", analyze_step)
    graph.add_edge(START, "analyze_step")
    graph.add_edge("analyze_step", END)
    stream = graph.compile().stream_events(state, version="v3")
    tokens = []
    for message in stream.messages:
        assert message.node == "analyze_step"
        tokens.extend(message.text)
    output = stream.output
    assert len(tokens) > 1
    assert "".join(tokens) == output["step_results"][-1]["conclusion"]
    assert output["step_index"] == 2 and output["step_plan"] is None
    assert state == before


if __name__ == "__main__":
    test_analyze_step()
    print("analyze_step and Event Streaming v3: PASS")
