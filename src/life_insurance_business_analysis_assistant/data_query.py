"""独立于 LangGraph 的查询边界；真实 API 尚未接入。"""

from collections.abc import Callable
from copy import deepcopy
from typing import TypeAlias

from life_insurance_business_analysis_assistant.agent.state import (
    DataRequirement, DatasetRecord, QueryCapabilities, QueryRequest, SlotValue, StepData,
)
from life_insurance_business_analysis_assistant.data_coverage import metric_ranges, validate_dataset, make_request


QueryData: TypeAlias = Callable[[QueryRequest], DatasetRecord]


class DataQueryError(RuntimeError):
    """查询失败，不能当作空数据继续执行。"""


def fake_capabilities() -> QueryCapabilities:
    """现有样例的明确能力；不是实际问数服务的契约或生产指标目录。"""
    monthly = ["标保达成", "标保达成率", "标保同比", "价值达成", "价值达成率", "价值同比"]
    annual = ["全年标保达成", "全年标保进度", "全年标保同比", "全年价值进度", "全年价值同比"]
    detail = {"标保达成率", "全年标保进度", "价值达成率"}
    return QueryCapabilities(
        source_id="report-example", source_version="sample-v1", population="sample",
        grains={"system": [], "institution": ["机构"]}, stable_entity_keys=True,
        metrics={metric: {"period": "month" if metric in monthly else "ytd",
                          "unit": "万元" if metric in ("标保达成", "全年标保达成") else None if metric == "价值达成" else "%",
                          "grains": ["system", "institution"] if metric in detail else ["system"]}
                 for metric in monthly + annual},
    )


def make_fake_query(query_params: dict[str, SlotValue]) -> QueryData:
    """为明确指定的参数注册两个场景的总体和模拟机构明细。

    数值参考 docs/月度分析报告-示例.md。该文件未给出年月；传入参数
    仅用于 POC 请求匹配，不代表这些数字真实属于该年月。
    """
    expected = deepcopy(query_params)
    samples = [
        {"标保达成": 12444, "标保达成率": "61.8%", "标保同比": "-11.6%",
         "全年标保达成": 100538, "全年标保进度": "53.8%", "全年标保同比": "20.6%"},
        {"价值达成": 7045, "价值达成率": "74.1%", "价值同比": "9.8%",
         "全年价值进度": "54.2%", "全年价值同比": "7.2%"},
    ]
    # 名单来自报告；逐机构百分比为人工构造，不是报告原始数据。
    groups = {
        "标保达成率": ("新疆 天津 潍坊 云南 海南 河南 内蒙古 宁波 甘肃", "贵州 安徽 山西 上海 青岛 宁夏 北京 深圳", 80, 40),
        "全年标保进度": ("宁波 新疆 贵州 潍坊 天津 甘肃 云南", "安徽 海南 宁夏 青岛 北京 深圳", 80, 30),
        "价值达成率": ("河南 天津 云南 吉林 新疆", "宁波 贵州 山西 青岛 宁夏 北京 上海 深圳", 95, 40),
    }
    institutions = sorted({name for high, low, _, _ in groups.values() for name in (high + " " + low).split()})
    details: dict[str, list[dict[str, str]]] = {}
    for metric, (high, low, high_value, low_value) in groups.items():
        values = dict.fromkeys(institutions, 50 if metric == "全年标保进度" else 60)
        values.update({name: high_value - rank for rank, name in enumerate(high.split())})
        values.update(dict.fromkeys(low.split(), low_value))
        details[metric] = [{"机构": name, metric: f"{value}%"} for name, value in values.items()]

    def sample_data(metrics: list[str], params: dict[str, SlotValue]) -> StepData:
        # ponytail: Fake 显式映射样例请求，真实粒度字段需等问数契约确定。
        if params != expected or any(type(params[k]) is not type(v) for k, v in expected.items()):
            raise DataQueryError("Fake 未配置该组查询参数")
        # 当前模板的分析对象“机构”对应这套全系统机构样例；请求范围仍按原值精确匹配。
        if params.get("机构范围") not in ("全系统", "机构"):
            raise DataQueryError("Fake 总体样例仅支持全系统范围")
        for row in samples:
            if metrics == list(row):
                return deepcopy({
                    "is_mock": True,
                    "source": "docs/月度分析报告-示例.md",
                    "scope": "全系统",
                    "query_params": dict(params),
                    "rows": [row],
                    "unit_notes": "标保达成、全年标保达成单位为万元；价值达成单位原文未注明；比率使用百分数字符串。",
                    "notice": "样例未注明年月，查询参数仅用于模拟请求匹配。",
                })
        if len(metrics) == 1 and metrics[0] in details:
            return deepcopy({
                "is_mock": True, "scope": "全系统模拟机构集合",
                "source": "docs/月度分析报告-示例.md（机构名单）",
                "query_params": dict(params), "rows": details[metrics[0]],
                "unit_notes": "比率使用百分数字符串。",
                "notice": "逐机构百分比为人工构造，仅供循环测试；机构集合不是完整真实全系统，年月仅用于模拟请求匹配。",
            })
        raise DataQueryError("Fake 未配置该组指标；不支持推断总体或明细粒度")

    capabilities = fake_capabilities()

    def query_data(request: QueryRequest) -> DatasetRecord:
        requirement = request["requirement"]
        if make_request(requirement, capabilities) != request:
            raise DataQueryError("Fake 请求标识或数据源不匹配")
        metrics = requirement["metrics"]
        if set(metrics) - capabilities["metrics"].keys():
            raise DataQueryError("Fake 未配置该组指标")
        grain = requirement["grain"]
        if grain not in capabilities["grains"] or any(grain not in capabilities["metrics"][m]["grains"] for m in metrics):
            raise DataQueryError("Fake 不支持该粒度")
        if grain == "system":
            sample = next((row for row in samples if set(metrics) <= row.keys()), None)
            if sample is None:
                raise DataQueryError("Fake 不支持该指标组合")
            data = sample_data(list(sample), expected)
            data["rows"] = [{m: sample[m] for m in metrics}]
        else:
            data = sample_data([metrics[0]], expected)
            # 仅组合原有样例中的值；不补造未配置的机构指标。
            indexes = {m: {r["机构"]: r[m] for r in details[m]} for m in metrics}
            data["rows"] = [{"机构": name, **{m: indexes[m][name] for m in metrics}} for name in institutions]
        coverage = DataRequirement(
            requirement_id="sample-response", metrics=list(metrics),
            time_ranges=metric_ranges(metrics, expected["年份"], expected["月份"], capabilities),
            grain=grain, dimensions=capabilities["grains"][grain],
            scope={key: value for key, value in expected.items() if key not in ("年份", "月份")},
            filters=[], completeness="full",
        )
        record = DatasetRecord(
            request_key=request["request_key"], source_id=capabilities["source_id"],
            source_version=capabilities["source_version"], population="sample", coverage=coverage,
            complete=True, truncated=False, units={m: capabilities["metrics"][m]["unit"] for m in metrics}, data=data,
        )
        try:
            return validate_dataset(record, request)
        except ValueError as error:
            raise DataQueryError("Fake 未配置该时间、范围或数据需求") from error

    return query_data
