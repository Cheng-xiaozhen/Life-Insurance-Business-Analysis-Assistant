"""报告模板 YAML 存储，供 Next 管理页面调用。"""

import json
import os
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class TemplateModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class Analysis(TemplateModel):
    id: str = Field(default_factory=lambda: str(uuid4()), exclude=True)
    text: str = Field(alias="分析步骤", min_length=1)
    metrics: list[str] = Field(alias="关联指标")
    mode: str = Field(alias="分析模式")


class Subchapter(TemplateModel):
    id: str = Field(default_factory=lambda: str(uuid4()), exclude=True)
    name: str = Field(alias="子板块名称", min_length=1)
    steps: list[Analysis] = Field(alias="分析步骤", min_length=1)


class Chapter(Analysis):
    name: str = Field(alias="板块名称", min_length=1)
    text: str = Field(alias="分析逻辑", min_length=1)
    children: list[Subchapter] = Field(alias="子板块")


class Report(TemplateModel):
    code: str = Field(alias="报告编码", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
    name: str = Field(alias="报告名称", min_length=1)
    channel: str = Field(alias="渠道类型")
    period: str = Field(alias="时间维度")
    target: str = Field(alias="分析对象")
    purpose: str = Field(alias="分析目的")
    chapters: list[Chapter] = Field(alias="章节板块", min_length=1)
    tone: str = Field(alias="语气风格")
    conclusion: str = Field(alias="结论风格")
    units: str = Field(alias="单位规则")
    examples: list[str] = Field(alias="句式示例")

    @field_validator("code")
    @classmethod
    def valid_filename(cls, value):
        if re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", value):
            raise ValueError("报告编码不能使用系统保留文件名")
        return value


def frontend(report: Report) -> dict:
    value = report.model_dump()
    for chapter, source in zip(value["chapters"], report.chapters):
        chapter["id"] = source.id
        for child, original in zip(chapter["children"], source.children):
            child["id"] = original.id
            for step, item in zip(child["steps"], original.steps):
                step["id"] = item.id
    return value


def read_report(file: Path) -> Report:
    if file.is_symlink():
        raise ValueError(f"不支持符号链接模板：{file.name}")
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"模板必须是映射：{file.name}")
    style = raw.pop("写作风格与格式要求")
    for chapter in raw["章节板块"]:
        for child in chapter["子板块"]:
            for step in child["分析步骤"]:
                if type(step.pop("步骤序号")) is not int:
                    raise ValueError("步骤序号必须为整数")
                # 排列顺序是步骤的实际顺序，保存时重新编号。
    report = Report.model_validate({**raw, **style})
    if file.name != f"{report.code}.yaml":
        raise ValueError(f"文件名必须与报告编码一致：{file.name}")
    return report


def list_reports(directory: Path) -> list[dict]:
    return [frontend(read_report(file)) for file in sorted(directory.glob("*.yaml"))]


def save_report(directory: Path, payload: dict) -> dict:
    report = Report.model_validate(payload["report"])
    original = payload.get("originalCode")
    if original is not None:
        original = Report.model_validate({**frontend(report), "code": original}).code
    directory.mkdir(parents=True, exist_ok=True)
    # ponytail: directory lock serializes local saves; use a database for multi-host editing.
    lock = directory / ".save.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("其他报告正在保存，请稍后重试") from None
    os.close(descriptor)
    temporary = None
    try:
        target = directory / f"{report.code}.yaml"
        source = directory / f"{original}.yaml" if original is not None else None
        if target.is_symlink() or (source and source.is_symlink()):
            raise ValueError("不支持符号链接模板")
        if any(file.stem.casefold() == report.code.casefold() and file.stem != original
               for file in directory.glob("*.yaml")):
            raise ValueError("报告编码已存在，请使用其他编码")
        if source and not source.is_file():
            raise ValueError("原报告文件不存在，请刷新后重试")
        if source:
            read_report(source)
        raw = report.model_dump(by_alias=True)
        raw["写作风格与格式要求"] = {key: raw.pop(key) for key in ("语气风格", "结论风格", "单位规则", "句式示例")}
        for chapter in raw["章节板块"]:
            for child in chapter["子板块"]:
                child["分析步骤"] = [{"步骤序号": index, **step} for index, step in enumerate(child["分析步骤"], 1)]
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            yaml.safe_dump(raw, stream, allow_unicode=True, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        if source and source.resolve() != target.resolve():
            try:
                source.unlink()
            except OSError:
                target.unlink()
                raise
        return frontend(report)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        lock.unlink()


def main():
    directory = Path(sys.argv[1])
    try:
        payload = json.load(sys.stdin)
        if payload["action"] == "list":
            result = {"reports": list_reports(directory)}
        elif payload["action"] == "save":
            result = {"report": save_report(directory, payload)}
        else:
            raise ValueError("不支持的操作")
        print(json.dumps(result, ensure_ascii=False))
    except ValidationError:
        print(json.dumps({"error": "模板字段无效；报告编码须为字母或数字开头，仅含字母、数字、下划线和连字符，最长100字符，不能使用系统保留名称。", "status": 400}, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        print(json.dumps({"error": f"报告模板操作失败：{error}", "status": 400}, ensure_ascii=False))
    except OSError:
        print(json.dumps({"error": "无法读写报告文件，请检查目录权限和磁盘空间。", "status": 500}, ensure_ascii=False))


if __name__ == "__main__":
    main()
