"""块 6：创新点 B 追问。签名已冻结。

复用评测时的 Dify 会话（同一个 conversation_id 和 user），只回答问题，不改报告、不重新计分。
提问模板由块 5 写在 agent/prompts/followup.md。
"""
import time

from app.core import prompts, storage
from app.core.dify_client import DifyClient
from app.core.storage import now_iso
from app.schemas import FollowupRequest, FollowupResponse, Report


def _defect_text(report: Report, index: int | None) -> str:
    if index is None:
        return "（未指定）"
    d = report.defects[index]
    return f"[{d.severity}] {d.type_name} {d.path}:{d.line} {d.title}"


def answer_followup(report: Report, req: FollowupRequest, dify: DifyClient) -> FollowupResponse:
    """在评测会话上追问一条，不改报告、不重新计分。DifyError 交给调用方。"""
    task_id = report.task_id
    user = f"task-{task_id}"
    conversation_id = report.conversation_id
    query = prompts.render(
        "followup",
        task_id=task_id,
        project_id=report.project.project_id,
        defect=_defect_text(report, req.defect_index),
        question=req.question,
    )
    existing = storage.read_tool_calls(task_id)
    before = max((r.seq for r in existing), default=0)
    res = dify.chat(query, user, conversation_id)
    for thought in res.thoughts:
        if thought.tool.startswith("dataset_"):
            t0 = time.monotonic()
            storage.append_tool_call(task_id, {
                "source": "followup",
                "tool": "knowledge",
                "input": {},
                "status": "passed",
                "started_at": now_iso(),
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "summary": f"检索知识库：{thought.tool_input[:80]}",
                "evidence_ids": [],
            })
    return FollowupResponse(answer=res.answer.strip(), tool_calls=storage.read_tool_calls(task_id, before))
