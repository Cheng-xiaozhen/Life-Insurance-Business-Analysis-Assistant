"""加载选定场景，只校验模板，不抽取槽位或执行分析。"""

import re
from typing import Any, TypedDict

from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.scenario_store import read_scenarios

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.state import (
    AgentState,
    ScenarioStep,
    ScenarioTemplate,
    SlotDefinition,
)


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


def _slot(value: Any, location: str) -> SlotDefinition:
    raw = _mapping(value, location)
    kind = raw.get("类型")
    if kind not in ("string", "integer"):
        raise ValueError(f"{location}.类型 仅支持 string 或 integer")
    if type(raw.get("必填")) is not bool:
        raise ValueError(f"{location}.必填 必须是布尔值")
    result = SlotDefinition(
        description=_text(raw.get("说明"), f"{location}.说明"),
        type=kind,
        required=raw["必填"],
    )
    for source, target in (("最小值", "minimum"), ("最大值", "maximum")):
        if source in raw:
            if kind != "integer" or type(raw[source]) is not int:
                raise ValueError(f"{location}.{source} 仅支持整数槽位的整数边界")
            if target == "minimum":
                result["minimum"] = raw[source]
            else:
                result["maximum"] = raw[source]
    if "minimum" in result and "maximum" in result:
        if result["minimum"] > result["maximum"]:
            raise ValueError(f"{location} 最小值不能大于最大值")
    if "默认值" in raw:
        default = raw["默认值"]
        if kind == "integer":
            if type(default) is not int:
                raise ValueError(f"{location}.默认值 必须是整数")
            if ("minimum" in result and default < result["minimum"]) or (
                "maximum" in result and default > result["maximum"]
            ):
                raise ValueError(f"{location}.默认值 超出允许范围")
        else:
            _text(default, f"{location}.默认值")
        result["default"] = default
    return result


def _check_references(text: str, slots: dict[str, SlotDefinition], location: str) -> None:
    """只检查占位符声明，不替换内容或改变参数类型。"""
    pattern = r"\{\{([^{}]+)\}\}"
    for name in re.findall(pattern, text):
        if name not in slots:
            raise ValueError(f"{location} 引用了未声明槽位: {name}")
    remainder = re.sub(pattern, "", text)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError(f"{location} 包含无效槽位占位符")


def load_template(
    state: AgentState, runtime: Runtime[AgentContext]
) -> LoadTemplateUpdate:
    """按编码加载唯一场景，校验成功后一次性返回 template 更新。"""
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
    slot_source = _mapping(source.get("输入参数", {}), f"{scenario_id}.输入参数")
    slots = {name: _slot(value, f"槽位 {name}") for name, value in slot_source.items()}
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
        _check_references(text, slots, location)
        params = _mapping(step.get("取数参数", {}), f"{location}.取数参数")
        for name, value in params.items():
            if type(value) not in (str, int):
                raise ValueError(f"{location}.取数参数.{name} 必须是字符串或整数")
            if isinstance(value, str):
                _text(value, f"{location}.取数参数.{name}")
                _check_references(value, slots, f"{location}.取数参数.{name}")
        normalized = ScenarioStep(
            step_id=step_id, text=text,
            metrics=[] if step.get("指标") == [] else _texts(step.get("指标"), f"{location}.指标"),
            query_params=dict(params),
        )
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
        slot_definitions=slots,
        steps=steps,
    )
    return LoadTemplateUpdate(template=template)
