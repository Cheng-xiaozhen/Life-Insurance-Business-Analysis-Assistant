"""绑定当前步骤的参数并取数，不执行分析或推进步骤。"""

import json
import re
from typing import TypedDict

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.state import AgentState, SlotValue, StepData
from life_insurance_business_analysis_assistant.data_query import DataQueryError


class FetchStepDataUpdate(TypedDict):
    """仅保存当前步骤的查询结果。"""

    current_data: StepData


def fetch_step_data(state: AgentState, runtime: Runtime[AgentContext]) -> FetchStepDataUpdate:
    template = state["template"]
    index = state["step_index"]
    if template is None or state["clarification"] is not None:
        raise ValueError("取数需要已加载模板且没有待解决追问")
    if type(index) is not int or not 0 <= index < len(template["steps"]):
        raise ValueError("step_index 超出当前模板步骤范围")
    step = template["steps"][index]
    metrics = step["metrics"]
    if not metrics or any(not isinstance(m, str) or not m.strip() for m in metrics):
        # 检查当前步骤是否声明有效指标，只有有指标时才会取数
        raise ValueError("当前步骤必须声明有效指标")
    slots = state["slots"]
    # 检查模板声明的必填槽位是否都已经存在
    for name, definition in template["slot_definitions"].items():
        if definition["required"] and name not in slots:
            raise ValueError(f"缺少必填槽位: {name}")

    def slot(name: str) -> SlotValue:
        """
        槽位读取函数
        """
        if name not in template["slot_definitions"] or name not in slots:
            # 确保模板中确实声明该槽位
            raise ValueError(f"查询参数引用的槽位未声明或缺失: {name}")
        value = slots[name]
        if type(value) not in (str, int):
            # 确保槽位值是字符串或整数类型
            raise ValueError(f"槽位 {name} 的类型无效")
        return value # 返回槽位值

    params: dict[str, SlotValue] = {}
    pattern = r"\{\{([^{}]+)\}\}"
    for key, value in step["query_params"].items():
        if isinstance(value, str):
            remainder = re.sub(pattern, "", value)
            if "{{" in remainder or "}}" in remainder:
                raise ValueError(f"取数参数 {key} 的占位符无效")
            match = re.fullmatch(pattern, value)
            params[key] = slot(match[1]) if match else re.sub(
                pattern, lambda m: str(slot(m[1])), value
            )
        elif type(value) is int:
            params[key] = value
        else:
            raise ValueError(f"取数参数 {key} 的类型无效")
    query = runtime.context.query_data
    if query is None:
        raise DataQueryError("未配置数据查询函数")
    data = query(list(metrics), params)
    if not isinstance(data, dict):
        raise DataQueryError("查询结果必须是可序列化的数据字典")
    try:
        json.dumps(data, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise DataQueryError("查询结果不是有效的 JSON 数据") from error
    return FetchStepDataUpdate(current_data=data)
