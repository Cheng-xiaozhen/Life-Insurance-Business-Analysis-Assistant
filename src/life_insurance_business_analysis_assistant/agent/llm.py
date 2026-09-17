"""Optional LangChain model initialization.

The ReportAgent itself is usable without an API key.  Keeping model creation
lazy is useful for the PoC because deterministic query and rendering tests do
not need network access.
"""


from functools import lru_cache

from life_insurance_business_analysis_assistant.settings import settings


@lru_cache(maxsize=2)
def get_llm(*, thinking: bool):
    """按思考模式缓存模型，节点显式选择，不修改共享实例。"""
    api_key = settings.deepseek_api_key
    if not api_key:
        return None
    from langchain.chat_models import init_chat_model

    return init_chat_model(
        model=settings.deepseek_model,
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        model_provider=settings.deepseek_model_provider,
        temperature=0,
        extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}},
    )


if __name__ == "__main__":
    llm = get_llm(thinking=False)
    print(llm.invoke("你好"))
