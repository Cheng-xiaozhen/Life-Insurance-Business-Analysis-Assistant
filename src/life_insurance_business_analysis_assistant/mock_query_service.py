"""LLM 生成独立步骤样例，不提供固定业务数值或真实查询失败回退。"""

from langgraph.constants import TAG_NOSTREAM
from langchain_core.exceptions import OutputParserException

from life_insurance_business_analysis_assistant.data_query import (
    DataQueryError, DataQueryRequest, DataQueryResult, validate_result,
)
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class MockQueryService:
    def __init__(self, llm):
        self.llm = llm

    def __call__(self, request: DataQueryRequest) -> DataQueryResult:
        if self.llm is None:
            raise DataQueryError("Mock 查询模型未配置，请设置 DEEPSEEK_API_KEY")
        request = DataQueryRequest.model_validate(request.model_dump()) # 校验请求

        messages = [
            ("system", load_prompt("mock_query")),
            ("human", request.model_dump_json()),
        ] # 构造LLM消息列表，包含系统提示和用户请求
        try:
            structured = self.llm.with_structured_output(DataQueryResult, method="function_calling") # LLM结构化输出
            for attempt in range(2): # 尝试两次生成结果，第一次失败则提示重新生成
                try:
                    raw = structured.invoke(messages, config={"tags": [TAG_NOSTREAM]})  # 调用LLM生成结果
                    return validate_result(raw, request) # 返回前进行数据校验
                except (ValueError, OutputParserException) as error:
                    if attempt:
                        raise
                    messages.append(("human", "上次结构校验失败，请重新生成完整结果并修正：" + str(error))) # 添加错误信息到消息列表
        except Exception as error:
            raise DataQueryError("Mock 数据生成失败或响应不满足契约") from error
