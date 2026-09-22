"""运行：python -B tests/test_prompt_loader.py；无需模型或网络。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


def test_prompt_loader():
    for name in ("match_scenario", "plan_step", "resolve_slots", "analyze_step", "summarize_scenario", "recommend_charts"):
        assert load_prompt(name).strip()
    for name in ("../settings", "..\\settings", "/settings", "C:\\settings", "", "resolve_slots.md"):
        try:
            load_prompt(name)
        except ValueError:
            pass
        else:
            raise AssertionError(f"非法名称未被拒绝: {name}")
    with TemporaryDirectory() as directory, patch(
        "life_insurance_business_analysis_assistant.prompt_loader.files", return_value=Path(directory)
    ):
        path = Path(directory) / "prompts" / "sample.md"
        path.parent.mkdir()
        for content in ('中文 {{参数名}} {"value": 1}\n', '修改后的 Prompt\n'):
            path.write_text(content, encoding="utf-8")
            assert load_prompt("sample") == content
        path.write_text(" \n", encoding="utf-8")
        try:
            load_prompt("sample")
        except ValueError:
            pass
        else:
            raise AssertionError("空 Prompt 未被拒绝")
        try:
            load_prompt("missing")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("缺失 Prompt 未报错")


if __name__ == "__main__":
    test_prompt_loader()
    print("Prompt loading, reload, literal braces and errors: PASS")
