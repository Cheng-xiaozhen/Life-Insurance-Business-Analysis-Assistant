"""本地 Studio 入口：真实 LLM、LLM Mock 查询。"""

from pathlib import Path

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_chat_graph
from life_insurance_business_analysis_assistant.data_service.mock_query_service import MockQueryService
from life_insurance_business_analysis_assistant.agent.llm import get_llm

template_path = Path(__file__).resolve().parents[3] / "config/templates/Scenario"
graph = build_chat_graph(studio_context=AgentContext(
    scenario_catalog=load_scenario_catalog(template_path),
    template_path=template_path,
    query_data=MockQueryService(get_llm(thinking=False)),
    report_template_path=template_path.parent / "Report",
))
