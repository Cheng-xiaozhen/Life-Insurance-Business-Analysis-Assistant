"""父图输入和业务子图输出的汇总契约。"""

from typing import Annotated, NotRequired
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import QuestionAnswerState
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.state import ReportOutput


class StudioInput(TypedDict):
    report_template_id: NotRequired[str | None]
    question: NotRequired[str | None]
    messages: NotRequired[Annotated[list[AnyMessage], add_messages]]


class ChatState(QuestionAnswerState, ReportOutput):
    """父图对外状态：接收并保存两个业务子图的输出。"""
