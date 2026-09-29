"""每步一次查询；全部响应校验成功后原子保存，不推进步骤。"""
import logging
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import AnalysisExecutionState, get_current_step
from life_insurance_business_analysis_assistant.data_query import DataQueryError, DataQueryRequest, validate_result

logger = logging.getLogger(__name__)


def build_request(state: AnalysisExecutionState) -> DataQueryRequest:
    step, template = get_current_step(state), state["template"]
    return DataQueryRequest.model_validate({
        "scenarioInfo": {key: template[key] for key in (
            "scenario_id", "name", "channel_type", "time_dimension", "analysis_object", "analysis_purpose"
        )},
        "step": {"step_id": step["step_id"], "text": step["text"]},
        "metrics": list(step["metrics"]),
    })


def saved_step_data(state: AnalysisExecutionState, request: DataQueryRequest) -> tuple[list[str], list[dict]]:
    records = [(key, record) for key, record in state["datasets"].items()
               if record["step_id"] == request.step.step_id]
    if not records:
        return [], []
    by_id = dict(records)
    ids = [f"step:{request.step.step_id}:table:{i}" for i in range(1, len(records) + 1)]
    if set(ids) != set(by_id) or any(record["request"] != request.model_dump() for _, record in records):
        raise ValueError("已保存的数据与当前步骤请求不一致")
    result = validate_result({"datasets": [by_id[key]["payload"] for key in ids]}, request)
    return ids, [table.model_dump() for table in result.datasets]


def fetch_step_data(state: AnalysisExecutionState, runtime: Runtime[AgentContext]) -> dict:
    """
    查询当前步骤所需的数据。
    """
    step = state["current_step"] # 获取当前分析步骤
    if step is None:
        raise ValueError("必须先加载当前分析步骤")
    
    if not step["metrics"]:
        raise ValueError("当前分析步骤没有关联指标，无需查询数据")
    request = build_request(state) # 构建请求对象,包含场景信息、当前步骤文本和当前步骤指标列表
    try:
        ids, _ = saved_step_data(state, request) # 检查该步骤以前是不是查成功过
        if ids: # 如果已经查过了,直接返回空字典,不再重复查询
            return {}
        
        # 如果没有查过，就进行查询
        query = runtime.context.query_data # 获取数据查询函数

        if query is None:
            raise DataQueryError("未配置数据查询函数")
        
        result = validate_result(query(request.model_copy(deep=True)), request) # 调用查询函数,并验证返回结果是否合法

        records = {
            f"step:{step['step_id']}:table:{index}": {
                "step_id": step["step_id"], "request": request.model_dump(), "payload": table.model_dump(),
            }
            for index, table in enumerate(result.datasets, 1)
        }
        if records.keys() & state["datasets"].keys():
            raise ValueError("数据集编号冲突")
    except Exception as error:
        logger.exception("查询失败 step_id=%s", step["step_id"])
        raise DataQueryError(f"步骤 {step['step_id']} 查询失败或响应不满足契约") from error
    return {"datasets": {**state["datasets"], **records}}
