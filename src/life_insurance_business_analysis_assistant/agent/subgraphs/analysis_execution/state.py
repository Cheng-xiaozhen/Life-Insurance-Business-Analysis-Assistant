"""分析子图的输入、内部状态和唯一输出契约。"""
from typing_extensions import TypedDict
from life_insurance_business_analysis_assistant.agent.contracts import DatasetRecord, ScenarioStep, ScenarioTemplate


class StepResult(TypedDict):
    """分析步骤的结果"""
    step_id: int # 步骤ID
    dataset_ids: list[str] # 数据集ID列表
    conclusion: str # 结论


class AnalysisExecutionInput(TypedDict):
    """分析子图的输入契约"""
    template: ScenarioTemplate # 场景模板


class AnalysisExecutionState(AnalysisExecutionInput):
    """分析子图的内部状态契约"""
    step_index: int # 当前分析步骤索引，从0开始
    current_step: ScenarioStep | None # 当前分析步骤，None表示尚未加载
    datasets: dict[str, DatasetRecord] # 已加载的数据集，键为dataset_id
    step_results: list[StepResult] # 已完成的分析步骤结果列表


class AnalysisExecutionResult(TypedDict):
    """分析子图的唯一输出契约"""
    datasets: dict[str, DatasetRecord] # 已加载的数据集，键为dataset_id
    step_results: list[StepResult] # 已完成的分析步骤结果列表


class AnalysisExecutionOutput(TypedDict):
    analysis_result: AnalysisExecutionResult


def get_current_step(state: AnalysisExecutionState) -> ScenarioStep:
    step = state["current_step"]
    if step is None:
        raise ValueError("必须先加载当前分析步骤")
    return step
