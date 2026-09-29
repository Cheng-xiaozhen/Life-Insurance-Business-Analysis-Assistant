"""
确认整个分析循环真的完整结束，然后把子图内部状态整理成唯一的业务输出 analysis_result。
"""
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import AnalysisExecutionOutput, AnalysisExecutionState


def finalize_subgraph(state: AnalysisExecutionState) -> AnalysisExecutionOutput:
    steps, results = state["template"]["steps"], state["step_results"]

    # 校验所有步骤是不是都执行完了
    if not steps or type(state["step_index"]) is not int or state["step_index"] != len(steps):
        raise ValueError("所有分析步骤完成后才能组装结果")
    # 是不是每一个步骤都有一个结果
    if [r["step_id"] for r in results] != [s["step_id"] for s in steps]:
        raise ValueError("步骤结果缺失、重复或顺序不匹配")
    # 校验每个步骤的结果是否有效
    for result in results:
        if not isinstance(result["conclusion"], str) or not result["conclusion"].strip():
            raise ValueError("步骤结论必须是非空文本")
        for dataset_id in result["dataset_ids"]:
            record = state["datasets"].get(dataset_id)
            if record is None or record["step_id"] != result["step_id"]:
                raise ValueError("步骤引用的数据集不存在或来源步骤不匹配")
    return {
        "analysis_result":{
            "datasets": state["datasets"],
            "step_results": results}
            }
