"""报告模板加载和确定性组装；分析与图表使用共享执行节点。"""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.chat import chat_message
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.nodes.prepare_chat import prepare_chat
from life_insurance_business_analysis_assistant.report_store import Report, read_report


def prepare_report(state):
    code = state.get("report_template_id")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", code):
        raise ValueError("请选择有效的报告模板")
    Report.valid_filename(code)
    update = prepare_chat(state)
    return {**update, "report_template_id": code, "report_id": update["analysis_id"],
            "status": "正在加载报告模板"}


def load_report_template(state, runtime: Runtime[AgentContext]):
    directory = runtime.context.report_template_path
    if directory is None:
        raise ValueError("未配置报告模板目录")
    report = read_report(Path(directory) / f"{state['report_template_id']}.yaml")
    sections, steps = [], []

    def add_step(source, section, local_id, guidance):
        if any(not m.strip() for m in source.metrics) or len(set(source.metrics)) != len(source.metrics):
            raise ValueError("报告指标不能为空或重复")
        step = {"step_id": len(steps) + 1, "text": source.text, "metrics": source.metrics,
                "analysis_mode": source.mode, "section_id": section["section_id"],
                "section_path": section["path"], "local_step_id": local_id, "guidance": guidance}
        if not source.metrics:
            if source.mode not in ("总结", "综合", "综合分析") and not re.match(r"^(总结|汇总|综合分析)", source.text):
                raise ValueError("无指标步骤必须明确标记为总结或综合分析")
            # 顶层总结覆盖此前报告步骤；子板块总结只引用本子板块的前序步骤。
            sources = [s["step_id"] for s in steps if section["parent_id"] is None
                       or s["section_id"] == section["section_id"]]
            if not sources:
                raise ValueError("总结步骤之前没有可引用的分析结论")
            step["source_step_ids"] = sources
        steps.append(step)

    for index, chapter in enumerate(report.chapters, 1):
        section = {"section_id": str(index), "parent_id": None, "name": chapter.name,
                   "path": [chapter.name], "level": 2}
        sections.append(section)
        if not chapter.children:
            add_step(chapter, section, 1, [])
            continue
        if chapter.metrics:
            raise ValueError(f"指导板块 {chapter.name} 不能同时配置取数指标")
        for child_index, child in enumerate(chapter.children, 1):
            child_section = {"section_id": f"{index}.{child_index}", "parent_id": str(index),
                             "name": child.name, "path": [chapter.name, child.name], "level": 3}
            sections.append(child_section)
            for local_id, step in enumerate(child.steps, 1):
                add_step(step, child_section, local_id, [chapter.text])
    template = {"report_id": report.code, "name": report.name, "channel_type": report.channel,
                "time_dimension": report.period, "analysis_object": report.target,
                "analysis_purpose": report.purpose, "steps": steps, "question": state["question"],
                "writing_style": {"语气风格": report.tone, "结论风格": report.conclusion,
                                  "单位规则": report.units, "句式示例": report.examples}}
    return {"template": template, "report_template": report.model_dump(), "report_sections": sections}


def display_value(value, unit, rules):
    """只转换有明确源单位的显示副本；阈值判断继续使用原始数据。"""
    if value is None:
        return "—", unit
    amount = re.search(r"金额单位\s*(亿元|万元|元)", rules)
    number = Decimal(str(value))
    if amount and unit in ("元", "万元", "亿元"):
        scale = {"元": Decimal(1), "万元": Decimal(10000), "亿元": Decimal(100000000)}
        target = amount.group(1)
        number = number * scale[unit] / scale[target]
        unit = target
    precision = re.search(r"百分比保留\s*(\d+)\s*位小数", rules) if unit == "%" else None
    if precision:
        digits = min(int(precision.group(1)), 10)
        return format(number.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), f".{digits}f"), unit
    return format(number, "f"), unit


def markdown_cell(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def dataset_table(record, rules):
    data = record["payload"]
    fields = data["dimensions"] + data["metrics"]
    units = {m: display_value(0, data["units"][m], rules)[1] for m in data["metrics"]}
    headers = [f"{f}（{units[f] or '单位未知'}）" if f in units else f for f in fields]
    lines = ["| " + " | ".join(map(markdown_cell, headers)) + " |", "| " + " | ".join("---" for _ in fields) + " |"]
    for row in data["rows"]:
        values = [display_value(row[f], data["units"][f], rules)[0] if f in units else row[f] for f in fields]
        lines.append("| " + " | ".join(map(markdown_cell, values)) + " |")
    if data["notice"]:
        lines.extend(["", "数据说明：" + data["notice"]])
    if not data["complete"]:
        lines.extend(["", "数据不完整，仅反映已返回记录。"])
    return "\n".join(lines)


def assemble_report(state):
    template, result = state["template"], state["analysis_result"]
    steps, outcomes = template["steps"], result["step_results"]
    if [s["step_id"] for s in steps] != [r["step_id"] for r in outcomes]:
        raise ValueError("报告步骤未完整执行")
    sections = deepcopy(state["report_sections"])
    section_ids = {s["section_id"] for s in sections}
    if len(section_ids) != len(sections) or any(s["section_id"] not in section_ids for s in steps):
        raise ValueError("报告章节归属不完整")
    rules = template["writing_style"]["单位规则"]
    charts = deepcopy(state["chart_recommendations"])
    step_sections = {s["step_id"]: s["section_id"] for s in steps}
    for chart in charts:
        if chart["step_id"] not in step_sections:
            raise ValueError("图表引用未知报告步骤")
        chart["section_id"] = step_sections[chart["step_id"]]
        if chart["dataset_id"] is not None:
            record = result["datasets"].get(chart["dataset_id"])
            if record is None or record["step_id"] != chart["step_id"]:
                raise ValueError("图表来源与章节步骤不一致")
        for metric in chart["metrics"]:
            source_unit = chart["units"][metric]
            precision = re.search(r"百分比保留\s*(\d+)\s*位小数", rules)
            if source_unit == "%" and precision:
                chart.setdefault("precision", {})[metric] = min(int(precision.group(1)), 10)
            for row in chart["data"]:
                row[metric] = float(display_value(row[metric], source_unit, rules)[0])
            chart["units"][metric] = display_value(0, source_unit, rules)[1]
    markdown = ["# " + template["name"]]
    for section in sections:
        pairs = [(step, outcome) for step, outcome in zip(steps, outcomes)
                 if step["section_id"] == section["section_id"]]
        ids = list(dict.fromkeys(d for _, outcome in pairs for d in outcome["dataset_ids"]))
        for step, outcome in pairs:
            for dataset_id in outcome["dataset_ids"]:
                if result["datasets"].get(dataset_id, {}).get("step_id") != step["step_id"]:
                    raise ValueError("报告引用的数据来源不一致")
        body = "\n\n".join(outcome["conclusion"] for _, outcome in pairs)
        parts = ["#" * section["level"] + " " + section["name"]]
        if body:
            parts.append(body)
        parts.extend(dataset_table(result["datasets"][key], rules) for key in ids)
        section_charts = [c for c in charts if c["section_id"] == section["section_id"]]
        section.update(body=body, step_ids=[s["step_id"] for s, _ in pairs], dataset_ids=ids,
                       markdown="\n\n".join(parts), charts=section_charts)
        markdown.append(section["markdown"])
    report = {"report_id": state["report_id"], "template_id": state["report_template_id"],
              "title": template["name"], "markdown": "\n\n".join(markdown), "sections": sections,
              "datasets": result["datasets"], "chart_recommendations": charts}
    return {"report_sections": sections, "report_result": report, "chart_recommendations": charts,
            "messages": [chat_message(state, "report", report["markdown"], report=report),
                         chat_message(state, "charts", "图表已按章节收录于报告。")], "status": "已完成"}
