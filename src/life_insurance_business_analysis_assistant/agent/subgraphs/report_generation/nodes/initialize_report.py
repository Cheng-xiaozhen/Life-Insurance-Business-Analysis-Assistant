from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import publish_report


def initialize_report(state):
    update = {"step_index": 0, "current_step": None, "datasets": {}, "step_results": [],
              "pending_result": None, "analysis_result": {"datasets": {}, "step_results": []}}
    return {**update, **publish_report({**state, **update})}
