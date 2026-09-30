from typing import TypedDict
from langchain_core.runnables import RunnableConfig
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.subgraphs.analysis_execution.state import AnalysisExecutionState
from life_insurance_business_analysis_assistant.agent.shared.contracts import StepResult
from life_insurance_business_analysis_assistant.agent.shared.execution import generate_step_result


class AnalyzeStepUpdate(TypedDict):
    """完整结论生成后同步保存结果、推进索引。"""

    step_results: list[StepResult]
    step_index: int


def analyze_step(state: AnalysisExecutionState, config: RunnableConfig) -> AnalyzeStepUpdate:
    result = generate_step_result(state, config)
    return {"step_results": [*state["step_results"], result], "step_index": state["step_index"] + 1}
