"""节点使用的运行上下文及 POC 场景目录读取。"""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from omegaconf import OmegaConf

from life_insurance_business_analysis_assistant.data_query import QueryData


class ScenarioEntry(TypedDict):
    """匹配所需的场景信息，不包含槽位和分析步骤。"""

    scenario_id: str  # 唯一场景编码。
    name: str  # 展示名称。
    keywords: list[str]  # 已去除首尾空白并去重的触发关键词。


@dataclass(frozen=True)
class AgentContext:
    """调用工作流前准备，不写入业务 State。"""

    scenario_catalog: list[ScenarioEntry]
    template_path: str | Path | None = None  # 场景 YAML 来源，加载节点调用前提供。
    query_data: QueryData | None = None  # 由调用方注入真实查询或 Fake，不自动回退。


def load_scenario_catalog(path: str | Path) -> list[ScenarioEntry]:
    """只校验目录字段；完整模板校验留给 load_template 节点。"""
    raw = OmegaConf.to_container(OmegaConf.load(path), resolve=False)
    if not isinstance(raw, dict) or not isinstance(raw.get("场景"), list):
        raise ValueError("场景目录必须包含 '场景' 列表")

    catalog: list[ScenarioEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(raw["场景"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 个场景必须是映射")
        scenario_id, name = item.get("场景编码"), item.get("场景名称")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"第 {index} 个场景编码必须是非空字符串")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"场景 {scenario_id} 的名称必须是非空字符串")
        scenario_id = scenario_id.strip()
        if scenario_id in seen:
            raise ValueError(f"场景编码重复: {scenario_id}")
        keywords = item.get("触发关键词")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError(f"场景 {scenario_id} 必须提供非空触发关键词列表")
        if any(not isinstance(word, str) or not word.strip() for word in keywords):
            raise ValueError(f"场景 {scenario_id} 的关键词必须是非空字符串")
        catalog.append(ScenarioEntry(
            scenario_id=scenario_id,
            name=name.strip(),
            keywords=list(dict.fromkeys(word.strip() for word in keywords)),
        ))
        seen.add(scenario_id)
    return catalog
