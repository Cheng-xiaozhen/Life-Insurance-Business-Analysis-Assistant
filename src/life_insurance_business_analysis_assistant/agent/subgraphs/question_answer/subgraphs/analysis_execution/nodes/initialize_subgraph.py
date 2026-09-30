"""初始化分析执行状态。"""

from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.subgraphs.analysis_execution.state import AnalysisExecutionInput


def initialize_subgraph(state: AnalysisExecutionInput) -> dict:
    if not state["template"]["steps"]:
        raise ValueError("分析模板必须包含步骤")
    return {
        "step_index": 0, 
        "current_step": None, 
        "datasets": {}, 
        "step_results": []
        }
