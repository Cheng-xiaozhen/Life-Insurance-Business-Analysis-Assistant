"""确定性的数据覆盖、请求去重和投影；不调用模型或查询服务。"""

import calendar
import hashlib
import json
import math
from copy import deepcopy
from datetime import date
from typing import Any

from pydantic import TypeAdapter

from life_insurance_business_analysis_assistant.agent.state import (
    AgentState, DataFilter, DataRequirement, DatasetRecord, DataUse,
    QueryCapabilities, QueryRequest, StepData, StepPlan,
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def numeric(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("指标值必须是有限数值或百分数字符串")
    if isinstance(value, str):
        value = value.strip().removesuffix("%")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("指标值必须是有限数值")
    return result


def metric_ranges(metrics: list[str], year: int, month: int, capabilities: QueryCapabilities) -> dict:
    if type(year) is not int or type(month) is not int:
        raise ValueError("年份和月份必须是整数")
    end = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    return {metric: {"start": date(year, 1 if capabilities["metrics"][metric]["period"] == "ytd" else month, 1).isoformat(),
                     "end": end} for metric in metrics}


def validate_requirement(requirement: DataRequirement) -> None:
    TypeAdapter(DataRequirement).validate_python(requirement, strict=True)
    metrics, dimensions = requirement["metrics"], requirement["dimensions"]
    if not requirement["requirement_id"].strip() or not requirement["grain"].strip() or not metrics:
        raise ValueError("数据需求必须声明编号、粒度及指标")
    if any(not x.strip() for x in metrics + dimensions) or len(set(metrics + dimensions)) != len(metrics + dimensions):
        raise ValueError("指标和维度不能为空或重复")
    if set(requirement["time_ranges"]) != set(metrics):
        raise ValueError("必须逐指标声明有效时间区间")
    for period in requirement["time_ranges"].values():
        if date.fromisoformat(period["start"]) > date.fromisoformat(period["end"]):
            raise ValueError("时间区间起点晚于终点")
    for name, value in requirement["scope"].items():
        if not name.strip() or type(value) not in (str, int) or (isinstance(value, str) and not value.strip()):
            raise ValueError("查询范围必须明确且非空")
    for condition in requirement["filters"]:
        if condition["field"] not in metrics + dimensions or not condition["values"]:
            raise ValueError("筛选字段不存在或筛选值为空")
        if condition["op"] != "in" and len(condition["values"]) != 1:
            raise ValueError("非 in 筛选必须只有一个值")
        if condition["op"] in ("gt", "gte", "lt", "lte"):
            numeric(condition["values"][0])
    canonical(requirement)


def make_request(requirement: DataRequirement, capabilities: QueryCapabilities) -> QueryRequest:
    validate_requirement(requirement)
    normalized = deepcopy(requirement)
    normalized["metrics"] = sorted(normalized["metrics"])
    normalized["dimensions"] = sorted(normalized["dimensions"])
    normalized["filters"] = sorted(normalized["filters"], key=canonical)
    for condition in normalized["filters"]:
        if condition["op"] == "in":
            condition["values"] = sorted(condition["values"], key=canonical)
    identity = {key: normalized[key] for key in normalized if key != "requirement_id"}
    identity.update({key: capabilities[key] for key in ("source_id", "source_version", "population")})
    return QueryRequest(request_key=hashlib.sha256(canonical(identity).encode()).hexdigest(),
                        source_id=capabilities["source_id"], source_version=capabilities["source_version"],
                        population=capabilities["population"], requirement=normalized)


def filter_rows(rows: list[dict], filters: list[DataFilter]) -> list[dict]:
    def matches(row: dict, condition: DataFilter) -> bool:
        field, op, values = condition["field"], condition["op"], condition["values"]
        if field not in row or row[field] is None:
            raise ValueError(f"筛选字段缺失: {field}")
        value = row[field]
        if op in ("eq", "in"):
            return any(type(value) is type(other) and value == other for other in values)
        left, right = numeric(value), numeric(values[0])
        return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[op]
    return [row for row in rows if all(matches(row, condition) for condition in filters)]


def covered_metrics(dataset: DatasetRecord, requirement: DataRequirement) -> set[str]:
    coverage = dataset["coverage"]
    if coverage["grain"] != requirement["grain"] or set(coverage["dimensions"]) != set(requirement["dimensions"]):
        return set()
    # ponytail: 范围仅精确匹配；机构子集用显式 in 筛选表达，不猜测机构层级包含关系。
    if canonical(coverage["scope"]) != canonical(requirement["scope"]):
        return set()
    if coverage["filters"] and sorted(coverage["filters"], key=canonical) != sorted(requirement["filters"], key=canonical):
        return set()
    if any(f["field"] not in coverage["metrics"] + coverage["dimensions"] for f in requirement["filters"]):
        return set()
    if requirement["completeness"] == "full" and (not dataset["complete"] or dataset["truncated"]):
        return set()
    return {metric for metric in requirement["metrics"] if metric in coverage["metrics"]
            and coverage["time_ranges"][metric] == requirement["time_ranges"][metric]}


def validate_dataset(raw: Any, request: QueryRequest) -> DatasetRecord:
    dataset = TypeAdapter(DatasetRecord).validate_python(raw, strict=True)
    canonical(dataset)
    validate_requirement(dataset["coverage"])
    for key in ("request_key", "source_id", "source_version", "population"):
        if dataset[key] != request[key]:
            raise ValueError(f"查询响应与请求的 {key} 不一致")
    if dataset["population"] == "sample" and dataset["data"].get("is_mock") is not True:
        raise ValueError("模拟数据必须明确标注 is_mock")
    if dataset["population"] == "business" and dataset["data"].get("is_mock") is True:
        raise ValueError("模拟数据不能声明为真实业务总体")
    requirement = request["requirement"]
    if not set(requirement["metrics"]) <= covered_metrics(dataset, requirement):
        raise ValueError("查询响应覆盖范围或完整性不足")
    rows = dataset["data"].get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("查询响应 rows 必须是记录列表")
    metrics, dimensions = dataset["coverage"]["metrics"], dataset["coverage"]["dimensions"]
    if set(dataset["units"]) != set(metrics):
        raise ValueError("查询响应必须逐指标声明单位（未知用 null）")
    keys = set()
    for row in rows:
        if any(field not in row for field in metrics + dimensions):
            raise ValueError("查询响应缺少已声明的字段")
        if any(row[field] is None for field in dimensions):
            raise ValueError("实体键不能为空")
        row_key = canonical([row[field] for field in dimensions])
        if row_key in keys:
            raise ValueError("查询响应在声明粒度上存在重复实体键")
        keys.add(row_key)
        for metric in metrics:
            if row[metric] is None:
                if dataset["complete"]:
                    raise ValueError("完整数据的指标不能缺失")
            else:
                numeric(row[metric])
    # 验证用于选择的列，不以缺列或空值伪装零命中。
    filter_rows(rows, requirement["filters"])
    return deepcopy(dataset)


def select_data(dataset: DatasetRecord, use: DataUse) -> StepData:
    fields = dataset["coverage"]["dimensions"] + use["metrics"]
    rows = filter_rows(dataset["data"]["rows"], use["selection_filters"])
    return {**deepcopy(dataset["data"]), "rows": [{key: row[key] for key in fields} for row in rows],
            "units": {metric: dataset["units"][metric] for metric in use["metrics"]},
            "coverage": deepcopy(dataset["coverage"]), "complete": dataset["complete"],
            "population": dataset["population"], "source_id": dataset["source_id"],
            "source_version": dataset["source_version"]}


def choose_data(requirement: DataRequirement, datasets: dict[str, DatasetRecord],
                capabilities: QueryCapabilities) -> tuple[list[DataUse], list[QueryRequest]]:
    candidates = []
    for dataset_id, dataset in datasets.items():
        if any(dataset[key] != capabilities[key] for key in ("source_id", "source_version", "population")):
            continue
        metrics = covered_metrics(dataset, requirement)
        if metrics:
            candidates.append((dataset_id, metrics))
    candidates.sort(key=lambda item: (-len(item[1]), item[0]))
    required = set(requirement["metrics"])
    uses: list[DataUse] = []
    for dataset_id, metrics in candidates:
        # 只有稳定快照和实体集合能安全补查列；否则整项需求重新查询。
        if not required <= metrics and not (capabilities["stable_entity_keys"] and capabilities["source_version"]
                                              and requirement["completeness"] == "full"):
            continue
        selected = metrics & required
        if selected:
            uses.append(DataUse(requirement_id=requirement["requirement_id"], dataset_id=dataset_id,
                                metrics=sorted(selected), selection_filters=deepcopy(requirement["filters"])))
            required -= selected
        if not required:
            break
    if not required:
        return uses, []
    # 筛选所依赖的指标也必须在补查中，以免对不同实体集合拼接。
    missing = required | {f["field"] for f in requirement["filters"] if f["field"] in requirement["metrics"]}
    query_requirement = {**deepcopy(requirement), "metrics": sorted(missing),
                         "time_ranges": {m: requirement["time_ranges"][m] for m in sorted(missing)}}
    return uses, [make_request(query_requirement, capabilities)]


def pending_queries(state: AgentState) -> list[QueryRequest]:
    plan = state["step_plan"]
    if plan is None:
        raise ValueError("当前步骤尚未生成执行计划")
    return [query for query in plan["queries"] if query["request_key"] not in state["datasets"]]


def plan_data_uses(plan: StepPlan, datasets: dict[str, DatasetRecord]) -> list[DataUse]:
    uses = deepcopy(plan["data_uses"])
    for query in plan["queries"]:
        if query["request_key"] not in datasets:
            raise ValueError("步骤查询尚未完成")
        requirement = query["requirement"]
        uses.append(DataUse(requirement_id=requirement["requirement_id"], dataset_id=query["request_key"],
                            metrics=requirement["metrics"], selection_filters=requirement["filters"]))
    return uses


def prepare_step_data(plan: StepPlan, datasets: dict[str, DatasetRecord]) -> tuple[list[DataUse], list[StepData]]:
    uses = plan_data_uses(plan, datasets)
    prepared: list[StepData] = []
    for requirement in plan["requirements"]:
        selected = [use for use in uses if use["requirement_id"] == requirement["requirement_id"]]
        supplied: set[str] = set()
        pieces = []
        for use in selected:
            dataset = datasets[use["dataset_id"]]
            if not set(use["metrics"]) <= covered_metrics(dataset, requirement):
                raise ValueError("计划引用的数据不能满足当前需求")
            supplied.update(use["metrics"])
            pieces.append(select_data(dataset, use))
        if supplied != set(requirement["metrics"]):
            raise ValueError("步骤需求尚未完整覆盖")
        dimensions = requirement["dimensions"]
        merged = deepcopy(pieces[0])
        if len(pieces) > 1:
            identity = [(p["source_id"], p["source_version"], p["population"]) for p in pieces]
            if not identity[0][1] or any(item != identity[0] for item in identity):
                raise ValueError("不能关联不同来源或未知快照的数据")
            def keyed(rows):
                return {canonical([row[d] for d in dimensions]): dict(row) for row in rows}
            rows = keyed(merged["rows"])
            for piece in pieces[1:]:
                incoming = keyed(piece["rows"])
                if rows.keys() != incoming.keys():
                    raise ValueError("补查结果实体集合不一致，不能安全关联")
                for key, row in incoming.items():
                    if any(field in rows[key] and rows[key][field] != value for field, value in row.items()):
                        raise ValueError("补查结果存在冲突值")
                    rows[key].update(row)
                for metric, unit in piece["units"].items():
                    if metric in merged["units"] and merged["units"][metric] != unit:
                        raise ValueError("补查结果单位不一致")
                merged["units"].update(piece["units"])
            merged["rows"] = list(rows.values())
            merged["notice"] = "；".join(dict.fromkeys(str(p.get("notice", "")) for p in pieces if p.get("notice")))
            merged["complete"] = all(p["complete"] for p in pieces)
        merged["coverage"] = deepcopy(requirement)
        merged["requirement_id"] = requirement["requirement_id"]
        prepared.append(merged)
    return uses, prepared
