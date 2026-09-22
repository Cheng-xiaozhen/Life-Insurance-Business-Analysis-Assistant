"""本地 Studio 入口：真实 LLM、固定示例月份的 Fake 查询。"""

from pathlib import Path

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.data_query import fake_capabilities, make_fake_query

template_path = Path(__file__).resolve().parents[3] / "config/templates/Scenario"
graph = build_graph(studio_context=AgentContext(
    scenario_catalog=load_scenario_catalog(template_path),
    template_path=template_path,
    query_data=make_fake_query({"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "机构"}),
    query_capabilities=fake_capabilities(),
))
