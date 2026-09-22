"""场景 YAML 读写；命令行供本地 Next 服务调用。"""

import json
import os
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Step(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1)
    metrics: list[str]
    mode: str
    queryParams: dict[str, str | int] = Field(default_factory=dict)


class Scenario(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
    name: str = Field(min_length=1)
    channel: str
    period: str
    target: str
    purpose: str
    keywords: list[str]
    steps: list[Step] = Field(min_length=1)

    @field_validator("code")
    @classmethod
    def valid_filename(cls, value):
        if re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", value):
            raise ValueError("场景编码不能使用系统保留文件名")
        return value


FIELDS = {"code": "场景编码", "name": "场景名称", "channel": "渠道类型",
          "period": "时间维度", "target": "分析对象", "purpose": "分析目的", "keywords": "触发关键词"}


def read_scenarios(path: str | Path) -> list[dict]:
    """读取单场景文件或由单场景文件组成的模板目录。"""
    path = Path(path)
    files = sorted([*path.glob("*.yaml"), *path.glob("*.yml")]) if path.is_dir() else [path]
    entries = []
    for file in files:
        if file.is_symlink():
            raise ValueError(f"不支持符号链接模板：{file.name}")
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"模板必须是映射：{file.name}")
        if "场景" in raw or "场景编码" not in raw:
            raise ValueError("模板必须是包含场景编码的单个场景，不支持场景合集")
        entries.append(raw)
    return entries


def to_frontend(raw: dict) -> dict:
    value = {key: raw.get(label, [] if key == "keywords" else "") for key, label in FIELDS.items()}
    value["steps"] = [{"text": step["分析步骤"], "metrics": step.get("指标", []),
                       "mode": step.get("分析模式") or "", "queryParams": step.get("取数参数", {})}
                      for step in sorted(raw["分析思路"], key=lambda step: step["步骤序号"])]
    return Scenario.model_validate(value).model_dump()


def save_scenario(directory: Path, payload: dict) -> dict:
    scenario = Scenario.model_validate(payload["scenario"])
    original = payload.get("originalCode")
    if original is not None:
        Scenario.model_validate({**scenario.model_dump(), "code": original})
    directory.mkdir(parents=True, exist_ok=True)
    # ponytail: directory lock serializes local saves; use a database for multi-host editing.
    lock = directory / ".save.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("其他场景正在保存，请稍后重试") from None
    os.close(descriptor)
    temporary = None
    try:
        target = directory / f"{scenario.code}.yaml"
        source = directory / f"{original}.yaml" if original is not None else None
        if target.is_symlink() or (source and source.is_symlink()):
            raise ValueError("不支持符号链接模板")
        entries = read_scenarios(directory)
        if any(item["场景编码"].casefold() == scenario.code.casefold()
               and item["场景编码"] != original for item in entries):
            raise ValueError("场景编码已存在，请使用其他编码")
        if source and not source.is_file():
            raise ValueError("原场景文件不存在，请刷新后重试")
        if target.exists() and (source is None or target.resolve() != source.resolve()):
            raise ValueError("目标文件已存在")
        old = read_scenarios(source)[0] if source else {}
        raw = {**old, **{label: getattr(scenario, key) for key, label in FIELDS.items()}}
        raw["分析思路"] = [{"步骤序号": index, "分析步骤": step.text,
                           "指标": step.metrics, **({"分析模式": step.mode} if step.mode else {}),
                           **({"取数参数": step.queryParams} if step.queryParams else {})}
                          for index, step in enumerate(scenario.steps, 1)]
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
                target.unlink()  # 原文件仍在，撤回未完成的重命名。
                raise
        return scenario.model_dump()
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        lock.unlink()


def main():
    directory = Path(sys.argv[1])
    try:
        payload = json.load(sys.stdin)
        if payload["action"] == "list":
            result = {"scenarios": [to_frontend(raw) for raw in read_scenarios(directory)]}
        elif payload["action"] == "save":
            result = {"scenario": save_scenario(directory, payload)}
        else:
            raise ValueError("不支持的操作")
        print(json.dumps(result, ensure_ascii=False))
    except ValidationError:
        print(json.dumps({"error": "模板字段无效；编码须为字母或数字开头，仅含字母、数字、下划线和连字符，最长100字符。", "status": 400}, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        print(json.dumps({"error": f"场景模板操作失败：{error}", "status": 400}, ensure_ascii=False))
    except OSError:
        print(json.dumps({"error": "无法读写场景文件，请检查目录权限和磁盘空间。", "status": 500}, ensure_ascii=False))


if __name__ == "__main__":
    main()
