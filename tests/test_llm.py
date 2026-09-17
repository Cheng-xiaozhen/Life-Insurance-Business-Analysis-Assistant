"""运行：python -B tests/test_llm.py；真实 LangChain 适配器，模拟 API 响应。"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import ChartDecision
from life_insurance_business_analysis_assistant.agent.nodes.resolve_slots import SlotExtraction
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


def test_llm():
    settings = SimpleNamespace(deepseek_api_key="test-key", deepseek_base_url="https://api.deepseek.com",
                               deepseek_model="deepseek-v4-flash", deepseek_model_provider="deepseek")
    get_llm.cache_clear()
    try:
        with patch("life_insurance_business_analysis_assistant.agent.llm.settings", settings):
            plain, thinking = get_llm(thinking=False), get_llm(thinking=True)
            assert plain is get_llm(thinking=False) and thinking is get_llm(thinking=True)
            assert plain is not thinking
            decision = {"recommended": False, "chart_type": None, "step_id": 1, "dimensions": [],
                        "metrics": [], "reason": "单条记录", "description": "阅读结论"}
            cases = [
                (plain, SlotExtraction, "function_calling", {
                    "role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function",
                    "function": {"name": "SlotExtraction", "arguments": '{"values": {}, "ambiguous": {}}'}}],
                }),
                (thinking, ChartDecision, "json_mode", {
                    "role": "assistant", "content": json.dumps(decision), "reasoning_content": "模拟思考内容",
                }),
            ]
            for model, schema, method, message in cases:
                response = {"id": "test", "model": settings.deepseek_model,
                            "choices": [{"index": 0, "message": message,
                                         "finish_reason": "tool_calls" if method == "function_calling" else "stop"}]}
                api = model.client.with_raw_response
                operation = "create" if method == "function_calling" else "parse"
                raw_response = SimpleNamespace(parse=lambda: response, headers={})
                with patch.object(api, operation, return_value=raw_response) as create:
                    result = model.with_structured_output(schema, method=method).invoke([
                        ("system", load_prompt("recommend_charts") + json.dumps(ChartDecision.model_json_schema(), ensure_ascii=False)),
                        ("human", "测试 JSON 输出"),
                    ])
                    assert isinstance(result, schema)
                    request = create.call_args.kwargs
                    expected = "disabled" if method == "function_calling" else "enabled"
                    assert request["extra_body"]["thinking"]["type"] == expected
                    if method == "function_calling":
                        assert request["tool_choice"]["function"]["name"] == "SlotExtraction"
                    else:
                        assert "tools" not in request and "tool_choice" not in request
                        assert request["response_format"] == {"type": "json_object"}
                        assert result.model_dump() == decision
                        response["choices"][0]["message"]["content"] = '{"recommended": "invalid"}'
                        try:
                            model.with_structured_output(schema, method=method).invoke("输出 JSON")
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("无效 JSON 决策必须被解析器拒绝")
    finally:
        get_llm.cache_clear()


if __name__ == "__main__":
    test_llm()
    print("LLM thinking modes, request parameters and JSON validation: PASS")
