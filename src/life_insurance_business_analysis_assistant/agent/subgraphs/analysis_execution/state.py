"""分析子图的输入、内部状态和唯一输出契约。"""
from typing_extensions import TypedDict
from life_insurance_business_analysis_assistant.agent.contracts import DatasetRecord, ScenarioStep, ScenarioTemplate


class StepResult(TypedDict):
    step_id: int
    dataset_ids: list[str]
    conclusion: str


class AnalysisExecutionInput(TypedDict):
    template: ScenarioTemplate


class AnalysisExecutionState(AnalysisExecutionInput):
    step_index: int
    current_step: ScenarioStep | None
    datasets: dict[str, DatasetRecord]
    step_results: list[StepResult]


class AnalysisExecutionResult(TypedDict):
    datasets: dict[str, DatasetRecord]
    step_results: list[StepResult]


class AnalysisExecutionOutput(TypedDict):
    analysis_result: AnalysisExecutionResult


def current_step(state: AnalysisExecutionState) -> ScenarioStep:
    step = state["current_step"]
    if step is None:
        raise ValueError("必须先加载当前分析步骤")
    return step
