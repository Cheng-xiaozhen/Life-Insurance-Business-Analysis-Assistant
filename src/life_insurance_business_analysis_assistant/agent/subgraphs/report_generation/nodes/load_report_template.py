from pathlib import Path
import re
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.report_store import read_report


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
