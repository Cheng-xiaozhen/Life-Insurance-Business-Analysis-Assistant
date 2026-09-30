"""报告子图的边界状态和内部执行状态。"""

from life_insurance_business_analysis_assistant.agent.shared.contracts import BusinessState, MessageState, DatasetRecord, ScenarioStep, StepResult


class ReportOutput(BusinessState, MessageState):
    report_template_id: str | None
    report_id: str | None
    report_template: dict | None
    report_sections: list[dict]
    report_result: dict | None


class ReportState(ReportOutput):
    step_index: int
    current_step: ScenarioStep | None
    datasets: dict[str, DatasetRecord]
    step_results: list[StepResult]
    pending_result: StepResult | None
