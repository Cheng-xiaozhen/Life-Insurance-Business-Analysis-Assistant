from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import re


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


def build_report(state, *, complete=False, charts_ready=False):
    template, result = state["template"], state["analysis_result"]
    steps, outcomes = template["steps"], result["step_results"]
    expected = steps if complete else steps[:len(outcomes)]
    if [s["step_id"] for s in expected] != [r["step_id"] for r in outcomes]:
        raise ValueError("报告步骤结果缺失或顺序错误")
    sections = deepcopy(state["report_sections"])
    section_ids = {s["section_id"] for s in sections}
    if len(section_ids) != len(sections) or any(s["section_id"] not in section_ids for s in steps):
        raise ValueError("报告章节归属不完整")
    rules = template["writing_style"]["单位规则"]
    charts = deepcopy(state.get("chart_recommendations") or [])
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
        by_step = {outcome["step_id"]: outcome for _, outcome in pairs}
        blocks = [{"step_id": step["step_id"], "text": by_step[step["step_id"]]["conclusion"] if step["step_id"] in by_step else "",
                   "status": "complete" if step["step_id"] in by_step else "pending"}
                  for step in steps if step["section_id"] == section["section_id"]]
        body = "\n\n".join(outcome["conclusion"] for _, outcome in pairs)
        parts = ["#" * section["level"] + " " + section["name"]]
        if body:
            parts.append(body)
        tables = "\n\n".join(dataset_table(result["datasets"][key], rules) for key in ids)
        if tables:
            parts.append(tables)
        section_charts = [c for c in charts if c["section_id"] == section["section_id"]]
        section.update(heading=parts[0], blocks=blocks, table_markdown=tables, body=body, step_ids=[s["step_id"] for s, _ in pairs], dataset_ids=ids,
                       markdown="\n\n".join(parts), charts=section_charts)
        markdown.append(section["markdown"])
    report = {"report_id": state["report_id"], "template_id": state["report_template_id"],
              "title": template["name"], "status": "complete" if complete else "generating",
              "revision": len(outcomes) + int(charts_ready) + int(complete), "markdown": "\n\n".join(markdown), "sections": sections,
              "datasets": result["datasets"], "chart_recommendations": charts}
    return report
