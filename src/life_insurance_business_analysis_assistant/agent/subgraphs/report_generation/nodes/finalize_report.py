from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import publish_report
from life_insurance_business_analysis_assistant.agent.shared.execution import finalize_execution


def finalize_report(state):
    finalize_execution(state)
    update = publish_report(state, complete=True, charts_ready=True)
    report = update["report_result"]
    return {**update, "report_sections": report["sections"],
            "chart_recommendations": report["chart_recommendations"]}
