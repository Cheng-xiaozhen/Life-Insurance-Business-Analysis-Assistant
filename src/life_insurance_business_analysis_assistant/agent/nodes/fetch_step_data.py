"""一次执行一个缺口查询；每份成功响应独立进入检查点。"""

import logging

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.state import AgentState, current_step
from life_insurance_business_analysis_assistant.data_coverage import make_request, pending_queries, validate_dataset
from life_insurance_business_analysis_assistant.data_query import DataQueryError

logger = logging.getLogger(__name__)


def fetch_step_data(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    step = current_step(state)
    plan = state["step_plan"]
    if state["clarification"] or plan is None or plan["step_id"] != step["step_id"]:
        raise ValueError("取数需要已确认的当前步骤计划")
    pending = pending_queries(state)
    if not pending:
        return {}
    query = runtime.context.query_data
    if query is None:
        raise DataQueryError("未配置数据查询函数")
    request = pending[0]
    logger.info("step_id=%s query=%s metrics=%s", step["step_id"], request["request_key"], request["requirement"]["metrics"])
    try:
        capabilities = runtime.context.query_capabilities
        if capabilities is None or make_request(request["requirement"], capabilities) != request:
            raise ValueError("数据源配置已变化，当前查询计划不可继续执行")
        data = validate_dataset(query(request), request)
        for metric in request["requirement"]["metrics"]:
            unit = capabilities["metrics"][metric]["unit"]
            if unit is not None and data["units"][metric] != unit:
                raise ValueError(f"查询响应指标单位不一致：{metric}")
    except Exception as error:
        logger.exception("查询失败 step_id=%s query=%s", step["step_id"], request["request_key"])
        raise DataQueryError(f"查询失败或响应不满足需求：{request['request_key'][:12]}") from error
    return {"datasets": {**state["datasets"], request["request_key"]: data}}
