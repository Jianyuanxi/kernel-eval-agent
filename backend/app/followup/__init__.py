"""块 6：创新点 B 追问。签名已冻结。

复用评测时的 Dify 会话（同一个 conversation_id 和 user），只回答问题，不改报告、不重新计分。
提问模板由块 5 写在 agent/prompts/followup.md。
"""
from app.core.dify_client import DifyClient
from app.schemas import FollowupRequest, FollowupResponse, Report


def answer_followup(report: Report, req: FollowupRequest, dify: DifyClient) -> FollowupResponse:
    raise NotImplementedError
