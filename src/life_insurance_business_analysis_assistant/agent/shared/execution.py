"""共用的步骤校验、查询与结论生成；由各图节点决定如何提交状态。"""

from life_insurance_business_analysis_assistant.agent.shared.contracts import ScenarioStep, StepResult
import logging
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.data_query import DataQueryError, DataQueryRequest, validate_result
import json
from langchain_core.runnables import RunnableConfig
from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.shared.messages import stream_text
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


def get_current_step(state: dict) -> ScenarioStep:
    step = state["current_step"]
    if step is None:
        raise ValueError("必须先加载当前分析步骤")
    return step


def load_execution_step(state: dict) -> dict[str,ScenarioStep]:
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


def build_request(state: dict) -> DataQueryRequest:
    step, template = get_current_step(state), state["template"]
    if "report_id" in template:
        return DataQueryRequest.model_validate({
            "reportInfo": {key: template[key] for key in (
                "report_id", "name", "channel_type", "time_dimension", "analysis_object", "analysis_purpose")},
            "question": template["question"], "section_path": step["section_path"],
            "guidance": step["guidance"], "step": {"step_id": step["step_id"], "text": step["text"]},
            "metrics": list(step["metrics"]),
        })
    return DataQueryRequest.model_validate({
        "scenarioInfo": {key: template[key] for key in (
            "scenario_id", "name", "channel_type", "time_dimension", "analysis_object", "analysis_purpose"
        )},
        "step": {"step_id": step["step_id"], "text": step["text"]},
        "metrics": list(step["metrics"]),
    })


def saved_step_data(state: dict, request: DataQueryRequest) -> tuple[list[str], list[dict]]:
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


def query_step_data(state: dict, runtime: Runtime[AgentContext]) -> dict:
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


def generate_step_result(state: dict, config: RunnableConfig, stream=stream_text) -> StepResult:
    """
    根据当前分析步骤，读取该步骤允许使用的证据，调用分析 LLM 生成结论；
    返回经校验的完整步骤结果；具体节点负责提交结果和推进索引。
    """
    step = get_current_step(state) # 获取当前步骤信息
    template, index = state["template"], state["step_index"] # 获取模板和步骤索引

    if [r["step_id"] for r in state["step_results"]] != [s["step_id"] for s in template["steps"][:index]]:
        # 检查前序步骤结果是否完整、顺序正确
        raise ValueError("前序步骤结果缺失、重复或顺序错误") 
    
    dataset_ids, datasets, conclusions = [], [], []
    if step["metrics"]: # 有指标步骤
        dataset_ids, datasets = saved_step_data(state, build_request(state))
        if not datasets:
            raise ValueError("当前步骤尚未成功取数")
    else: # 当前步骤无关联指标
        if any(record["step_id"] == step["step_id"] for record in state["datasets"].values()):
            raise ValueError("无指标步骤不能关联旧查询数据") # 如果这个步骤声明没有指标，但却有旧数据集关联，说明数据不一致
        conclusions = [{"step_id": r["step_id"], "conclusion": r["conclusion"]} for r in state["step_results"]] # 把之前完成步骤的结论拿出来，基于已有原子结论进行二次综合
        if "source_step_ids" in step:
            allowed = step["source_step_ids"]
            if not set(allowed) <= {r["step_id"] for r in conclusions}:
                raise ValueError("总结引用了尚未完成的步骤")
            conclusions = [r for r in conclusions if r["step_id"] in allowed]
    
    llm = get_llm(thinking=True)

    if llm is None:
        raise RuntimeError("分析模型未配置，请设置 DEEPSEEK_API_KEY")
    
    payload = {
        "scenario": {
            key: template[key]
              for key in (
                "name",
                "analysis_purpose",
                "channel_type",
                "time_dimension",
                "analysis_object"
        )},
        "step": {
            "step_id": step["step_id"],
            "text": step["text"],
            "analysis_mode": step.get("analysis_mode"),
            "metrics": step["metrics"]
            },
        "datasets": [
            {"dataset_id": key, **data}
            for key, data in zip(dataset_ids, datasets)
            ],
        "conclusions": conclusions,
    }
    if "report_id" in template:
        payload["report"] = payload.pop("scenario")
        payload.update(question=template["question"], writing_style=template["writing_style"],
                       section_path=step["section_path"], guidance=step["guidance"])
    heading = f"步骤 {step['step_id']}：{step['text']}"
    conclusion, message = stream(
        llm, 
        [
            ("system", load_prompt("analyze_step")),
            ("human", json.dumps(payload, ensure_ascii=False)),
    ],
    config,
    state,
    f"step:{step['step_id']}",
    heading
    )
    
    if message.tool_calls:
        raise RuntimeError("分析步骤不允许调用工具")
    if message.response_metadata.get("finish_reason") in ("length", "content_filter"):
        raise RuntimeError("分析结论未完整生成")
    if not conclusion:
        raise RuntimeError("分析模型未返回有效结论")
    
    result = StepResult(
        step_id=step["step_id"],
        dataset_ids=dataset_ids,
        conclusion=conclusion
        )
    return result


def finalize_execution(state: dict) -> dict:
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


logger = logging.getLogger(__name__)
