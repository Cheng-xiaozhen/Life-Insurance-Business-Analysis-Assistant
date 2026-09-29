"""分析子图的输入、内部状态和唯一输出契约。"""
from typing import NotRequired

from typing_extensions import TypedDict


class ScenarioStep(TypedDict):
    """一个普通分析步骤的模板配置。"""

    step_id: int  # 模板中的步骤序号，从 1 开始。
    text: str  # 自然语言分析说明。
    metrics: list[str]  # 本步骤需要查询的指标。
    analysis_mode: NotRequired[str | None]  # 可选分析模式，如条件筛选。


class ScenarioTemplate(TypedDict):
    """加载器规范化后的模板快照，运行期间不修改。"""

    scenario_id: str  # 场景唯一编码。
    name: str  # 场景展示名称。
    channel_type: str  # 场景适用渠道。
    time_dimension: str  # 时间粒度，如月度，不是具体年月。
    analysis_object: str  # 分析对象层级，如机构，不是具体机构范围。
    analysis_purpose: str  # 业务分析目的，如经营检视。
    keywords: list[str]  # 用于匹配场景的触发关键词。
    steps: list[ScenarioStep]  # 分析步骤 已按 step_id 排序。


class DatasetRecord(TypedDict):
    """一次成功查询中的一张表；以分析内 dataset_id 为键保存。"""

    step_id: int
    request: dict  # DataQueryRequest 的 JSON 快照。
    payload: dict  # 已经 DatasetPayload 校验的 JSON。


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
