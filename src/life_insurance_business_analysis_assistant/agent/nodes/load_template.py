"""加载选定场景，只校验模板，不执行分析。"""

from typing import Any, TypedDict

from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.scenario_store import read_scenarios

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.state import AgentState, ScenarioStep, ScenarioTemplate


class LoadTemplateUpdate(TypedDict):
    """仅写入本次使用的完整模板快照。"""

    template: ScenarioTemplate


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} 必须是非空字符串")
    return value.strip()


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not key.strip() for key in value
    ):
        raise ValueError(f"{location} 必须是非空字符串键的映射")
    return value


def _texts(value: Any, location: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{location} 必须是非空字符串列表")
    return [_text(item, location) for item in value]


def load_template(
    state: AgentState, runtime: Runtime[AgentContext]
) -> LoadTemplateUpdate:
    """
    按编码加载唯一场景，校验成功后一次性返回 template 更新。
    """
    scenario_id = _text(state["scenario_id"], "scenario_id")
    path = runtime.context.template_path
    if path is None:
        raise ValueError("加载模板前必须提供 AgentContext.template_path")
    entries = read_scenarios(path)
    selected = []
    for entry in entries:
        entry = _mapping(entry, "场景目录条目")
        if _text(entry.get("场景编码"), "场景编码") == scenario_id:
            selected.append(entry)
    if len(selected) != 1:
        raise ValueError(f"场景 {scenario_id} 必须唯一存在，实际找到 {len(selected)} 个")
    source = selected[0]
    raw_steps = source.get("分析思路")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError(f"场景 {scenario_id}.分析思路 必须是非空步骤列表")
    steps: list[ScenarioStep] = []
    for raw_step in raw_steps:
        step = _mapping(raw_step, "分析步骤")
        step_id = step.get("步骤序号")
        if type(step_id) is not int or step_id < 1:
            raise ValueError("步骤序号必须是正整数")
        location = f"步骤 {step_id}"
        text = _text(step.get("分析步骤"), f"{location}.分析步骤")
        if step.get("取数参数"):
            raise ValueError(f"{location} 不再支持取数参数，请移除旧查询配置")
        if "{{" in text or "}}" in text:
            raise ValueError(f"{location} 不支持运行时槽位占位符")
        normalized = ScenarioStep(
            step_id=step_id, text=text,
            metrics=[] if step.get("指标") == [] else _texts(step.get("指标"), f"{location}.指标"),
        )
        if len(set(normalized["metrics"])) != len(normalized["metrics"]):
            raise ValueError(f"{location}.指标 不能重复")
        if "分析模式" in step:
            mode = step["分析模式"]
            normalized["analysis_mode"] = None if mode is None else _text(mode, f"{location}.分析模式")
        steps.append(normalized)
    steps.sort(key=lambda step: step["step_id"])
    if [step["step_id"] for step in steps] != list(range(1, len(steps) + 1)):
        raise ValueError("步骤序号必须无重复，并从 1 连续递增")

    template = ScenarioTemplate(
        scenario_id=scenario_id,
        name=_text(source.get("场景名称"), "场景名称"),
        channel_type=_text(source.get("渠道类型"), "渠道类型"),
        time_dimension=_text(source.get("时间维度"), "时间维度"),
        analysis_object=_text(source.get("分析对象"), "分析对象"),
        analysis_purpose=_text(source.get("分析目的"), "分析目的"),
        keywords=[] if source.get("触发关键词") == [] else list(dict.fromkeys(_texts(source.get("触发关键词"), "触发关键词"))),
        steps=steps,
    )
    return LoadTemplateUpdate(template=template)
