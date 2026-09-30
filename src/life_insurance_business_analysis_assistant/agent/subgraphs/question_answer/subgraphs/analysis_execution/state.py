"""分析子图的输入、内部状态和唯一输出契约。"""

from typing_extensions import TypedDict
from life_insurance_business_analysis_assistant.agent.shared.contracts import ExecutionTemplate, ScenarioStep, DatasetRecord, StepResult, AnalysisExecutionResult


class AnalysisExecutionInput(TypedDict):
    """分析子图的输入契约"""
    template: ExecutionTemplate # 场景或报告的共用执行输入


class AnalysisExecutionState(AnalysisExecutionInput):
    """分析子图的内部状态契约"""
    step_index: int # 当前分析步骤索引，从0开始
    current_step: ScenarioStep | None # 当前分析步骤，None表示尚未加载
    datasets: dict[str, DatasetRecord] # 已加载的数据集，键为dataset_id
    step_results: list[StepResult] # 已完成的分析步骤结果列表


class AnalysisExecutionOutput(TypedDict):
    analysis_result: AnalysisExecutionResult
