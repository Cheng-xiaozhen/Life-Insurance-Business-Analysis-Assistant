"""加载并校验当前分析步骤。"""
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import AnalysisExecutionState


def load_step(state: AnalysisExecutionState) -> dict:
    steps, index = state["template"]["steps"], state["step_index"]
    if type(index) is not int or not 0 <= index < len(steps):
        raise ValueError("step_index 超出当前模板步骤范围")
    step = steps[index]
    if (not isinstance(step, dict) or type(step.get("step_id")) is not int
            or step["step_id"] != index + 1
            or not isinstance(step.get("text"), str) or not step["text"].strip()
            or not isinstance(step.get("metrics"), list)
            or any(not isinstance(m, str) or not m.strip() for m in step["metrics"])
            or len(set(step["metrics"])) != len(step["metrics"])):
        raise ValueError("当前分析步骤不合法")
    return {"current_step": step}
