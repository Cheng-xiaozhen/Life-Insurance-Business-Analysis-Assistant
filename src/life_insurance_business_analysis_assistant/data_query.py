"""独立问数契约，不依赖 LangGraph State 或查询规划。"""

import json
import math
from collections.abc import Callable
from datetime import date
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False) # 禁止额外字段，严格类型检查，禁止无穷大和 NaN


class ScenarioInfo(QueryModel):
    scenario_id: str = Field(description="场景唯一编码")
    name: str = Field(description="场景名称")
    channel_type: str = Field(description="渠道类型")
    time_dimension: str = Field(description="时间维度")
    analysis_object: str = Field(description="分析对象")
    analysis_purpose: str = Field(description="分析目的")


class QueryStep(QueryModel):
    step_id: int = Field(ge=1,description="分析步骤序号，从 1 开始")
    text: str = Field(min_length=1,description="分析步骤描述")


class DataQueryRequest(QueryModel):
    scenarioInfo: ScenarioInfo = Field(description="场景基本信息")
    step: QueryStep = Field(description="分析步骤信息")
    metrics: list[str] = Field(min_length=1, description="关联指标列表")

    @model_validator(mode="after")
    def check_fields(self):
        strings = [*self.scenarioInfo.model_dump().values(), self.step.text, *self.metrics]
        if any(not value.strip() for value in strings) or len(set(self.metrics)) != len(self.metrics):
            raise ValueError("请求文本不能为空，指标不能重复")
        return self


class DatasetPayload(QueryModel):
    dimensions: list[str] = Field(description="数据维度字段；总体数据可为空")
    metrics: list[str] = Field(min_length=1,description="数据指标字段，至少包含一个指标")
    rows: list[dict[str, str | int | float | None]] = Field(description="数据记录，每行字段必须与 dimensions 和 metrics 声明一致")
    units: dict[str, str | None] = Field(description="各指标单位，未知单位使用 null")
    is_mock: bool = Field(description="是否为模拟数据")
    complete: bool = Field(description="数据集在声明范围内是否完整")
    notice: str = Field(description="数据范围、限制及模拟数据等说明")
    time_dimensions: list[str] = Field(default_factory=list,description="dimensions 中属于时间轴的字段")

    @model_validator(mode="after")
    def check_table(self):
        fields = self.dimensions + self.metrics
        if any(not field.strip() for field in fields) or len(set(fields)) != len(fields):
            raise ValueError("指标和维度不能为空或重复")
        if set(self.units) != set(self.metrics) or any(u is not None and not u.strip() for u in self.units.values()):
            raise ValueError("必须逐指标声明单位，未知用 null")
        if len(set(self.time_dimensions)) != len(self.time_dimensions) or not set(self.time_dimensions) <= set(self.dimensions):
            raise ValueError("时间维度必须是实际维度的唯一子集")
        if (not self.rows or not self.complete or self.is_mock) and not self.notice.strip():
            raise ValueError("空表、部分数据和模拟数据必须说明限制")
        seen = set()
        for row in self.rows:
            if set(row) != set(fields):
                raise ValueError("记录字段必须与声明一致")
            for dimension in self.dimensions:
                value = row[dimension]
                if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
                    raise ValueError("维度键不能为空")
            key = canonical([row[d] for d in self.dimensions])
            if key in seen:
                raise ValueError("维度组合重复；不能隐式聚合")
            seen.add(key)
            for metric in self.metrics:
                value = row[metric]
                if value is None:
                    if self.complete:
                        raise ValueError("完整数据的指标不能缺失")
                elif type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("指标必须为有限数值；百分比使用数值配合 % 单位")
            for dimension in self.time_dimensions:
                date.fromisoformat(str(row[dimension]))
        return self


class DataQueryResult(QueryModel):
    datasets: list[DatasetPayload] = Field(min_length=1)


QueryData: TypeAlias = Callable[[DataQueryRequest], DataQueryResult]


class DataQueryError(RuntimeError):
    """查询失败，不得伪装为空数据继续分析。"""


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def numeric(value) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("指标必须为有限数值")
    return float(value)


def validate_result(raw, request: DataQueryRequest) -> DataQueryResult:
    # 重验 dump，防止 model_construct/model_copy 绕过边界校验
    """
    验证
    DataQueryResult本身是否合法
    返回指标是否完整对应请求
    同一指标跨表单位是否一致
    """
    result = DataQueryResult.model_validate(raw.model_dump() if isinstance(raw, DataQueryResult) else raw)
    supplied, units = set(), {}
    for table in result.datasets:
        supplied.update(table.metrics)
        for metric, unit in table.units.items():
            if metric in units and units[metric] != unit:
                raise ValueError("同一指标跨表单位不一致")
            units[metric] = unit
    if supplied != set(request.metrics):
        raise ValueError("返回指标必须完整对应请求，不得新增或遗漏")
    return result
