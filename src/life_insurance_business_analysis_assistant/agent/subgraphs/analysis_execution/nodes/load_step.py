"""加载并校验当前分析步骤。"""
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import AnalysisExecutionState
from life_insurance_business_analysis_assistant.agent.contracts import ScenarioStep

def load_step(state: AnalysisExecutionState) -> dict[str,ScenarioStep]:
    """
    根据子图当前的 step_index，从模板中取出“本轮要执行的分析步骤”，做一次结构校验，然后写入 current_step。
    """
    steps, index = state["template"]["steps"], state["step_index"] # 从状态中读取模板的步骤和当前索引
    if type(index) is not int or not 0 <= index < len(steps):
        raise ValueError("step_index 超出当前模板步骤范围")
    step = steps[index] # 从步骤中中取出当前步骤
    if (not isinstance(step, dict) or type(step.get("step_id")) is not int
            or step["step_id"] != index + 1
            or not isinstance(step.get("text"), str) or not step["text"].strip()
            or not isinstance(step.get("metrics"), list)
            or any(not isinstance(m, str) or not m.strip() for m in step["metrics"])
            or len(set(step["metrics"])) != len(step["metrics"])):
        raise ValueError("当前分析步骤不合法")
    return {"current_step": step}
