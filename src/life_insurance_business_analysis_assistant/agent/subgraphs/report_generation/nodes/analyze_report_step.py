from langchain_core.runnables import RunnableConfig
from life_insurance_business_analysis_assistant.agent.shared.execution import generate_step_result
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import stream_report_text
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.state import ReportState


def analyze_report_step(state: ReportState, config: RunnableConfig):
    # 生成和提交是两个节点；提交失败后无需再次调用模型。
    return {"pending_result": generate_step_result(state, config, stream=stream_report_text)}
