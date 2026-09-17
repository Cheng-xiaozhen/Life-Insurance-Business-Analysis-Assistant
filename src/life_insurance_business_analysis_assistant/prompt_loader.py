"""从包内 prompts 目录读取 UTF-8 Prompt，每次调用读取最新内容。"""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """按节点名加载同名 .md 文件；不插值，保留 JSON 和槽位花括号。"""
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError("Prompt 名称必须是有效标识符，不包含路径或扩展名")
    prompt = files(__package__).joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError(f"Prompt 不能为空: {name}")
    return prompt
