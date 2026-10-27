"""块 6 阶段 3：追问复用评测会话，不改报告。"""
import json

from app.config import EXAMPLES_DIR
from app.core import storage
from app.core.dify_client import ChatResult
from app.core.storage import TaskPaths
from app.followup import answer_followup
from app.schemas import AgentThought, FollowupRequest, Report


def _report() -> Report:
    return Report.model_validate_json((EXAMPLES_DIR / "report.json").read_text(encoding="utf-8"))


def _prepare(report: Report) -> bytes:
    paths = TaskPaths(report.task_id)
    paths.root.mkdir(parents=True, exist_ok=True)
    storage.write_json(paths.report, report)
    return paths.report.read_bytes()


class FakeDify:
    def __init__(self):
        self.calls: list[tuple] = []

    def chat(self, query: str, user: str, conversation_id: str = "", **kwargs) -> ChatResult:
        self.calls.append((query, user, conversation_id))
        return ChatResult(
            answer="  缓冲区写入前要检查 idx。  ",
            conversation_id=conversation_id or "new",
            thoughts=[
                AgentThought(id="k1", position=1, tool="dataset_os", tool_input="数组越界 内核栈", observation="命中"),
                AgentThought(id="t2", position=2, tool="read_source", tool_input="{}", observation=""),
            ],
        )


def test_followup_reuses_session_and_keeps_report():
    report = _report()
    before = _prepare(report)
    fake = FakeDify()
    defect = report.defects[0]
    req = FollowupRequest(question="为什么会越界？", defect_index=0)
    out = answer_followup(report, req, fake)

    assert len(fake.calls) == 1
    query, user, conv = fake.calls[0]
    assert user == f"task-{report.task_id}"
    assert conv == report.conversation_id
    assert defect.title in query
    assert "为什么会越界？" in query
    assert out.answer == "缓冲区写入前要检查 idx。"
    assert any(c.tool == "knowledge" and c.source == "followup" for c in out.tool_calls)
    assert "检索知识库：数组越界 内核栈" in {c.summary for c in out.tool_calls}
    assert TaskPaths(report.task_id).report.read_bytes() == before


def test_followup_without_defect_index():
    report = _report()
    _prepare(report)
    fake = FakeDify()
    answer_followup(report, FollowupRequest(question="总分怎么算的？", defect_index=None), fake)
    assert "（未指定）" in fake.calls[0][0]
