from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import publish_report


def commit_report_step(state):
    result = state["pending_result"]
    if result is None or result["step_id"] != state["current_step"]["step_id"]:
        raise ValueError("缺少当前步骤的完整结论")
    results = [*state["step_results"], result]
    update = {"step_results": results, "step_index": state["step_index"] + 1,
              "pending_result": None, "analysis_result": {"datasets": state["datasets"], "step_results": results}}
    return {**update, **publish_report({**state, **update})}
