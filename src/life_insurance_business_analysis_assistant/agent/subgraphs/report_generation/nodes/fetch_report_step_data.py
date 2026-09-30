from life_insurance_business_analysis_assistant.agent.shared.execution import query_step_data
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext


def fetch_report_step_data(state, runtime: Runtime[AgentContext]):
    return query_step_data(state, runtime)
