"""块 1 公共代码的边界检查：Codex 复查（2026-10-18）发现的问题各有一条回归测试。"""
import io
import json
import threading
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient

from app import config
from app.core import mocks, pipeline, storage
from app.core.storage import TaskPaths
from app.ingest import PathInvalidError
from app.main import app
from app.schemas import CodeLocation, DiffResult, Project, ReviewResult, ScanResult

TOKEN = {"X-Tool-Token": config.TOOL_TOKEN}


def _new_task() -> str:
    tid = storage.new_task_id()
    TaskPaths(tid).root.mkdir(parents=True)
    return tid


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_tools_openapi_is_valid_yaml():
    d = yaml.safe_load((config.REPO_DIR / "contracts" / "tools.openapi.yaml").read_text(encoding="utf-8"))
    ops = {op["operationId"] for p in d["paths"].values() for op in p.values()}
    assert ops == {"list_files", "read_source", "compile_project", "run_kernel", "clang_scan", "diff_reference"}


def test_mock_read_source_stays_inside_project(tmp_path):
    proj = tmp_path / "p1"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.c").write_text("int a;\nint b;\n", encoding="utf-8")
    (proj / "bin.dat").write_bytes(b"\x00\x01")
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    assert mocks.ingest.read_source(proj, "src/a.c", 1, 200).total_lines == 2
    for bad in ["../secret.txt", str(tmp_path / "secret.txt"), "src/none.c", "bin.dat", "src"]:
        with pytest.raises(PathInvalidError):
            mocks.ingest.read_source(proj, bad, 1, 10)


@pytest.mark.parametrize("text,n", [("", 0), ("a", 1), ("a\n", 1), ("a\r\nb\r\n\r\n", 3), ("a\n\nb", 3)])
def test_line_count_rule(tmp_path, text, n):
    p = tmp_path / "f.c"
    p.write_bytes(text.encode())
    assert len(mocks._lines(p)) == n


def test_mock_unzip_rejects_traversal(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("demo/src/a.c", "int a;\n")
        z.writestr("demo/../../evil.c", "int e;\n")
    up = tmp_path / "upload" / "x.zip"
    up.parent.mkdir()
    up.write_bytes(buf.getvalue())
    r = mocks.ingest.ingest_upload(tmp_path, [up], "x.zip")
    assert r.status == "failed" and r.error.code == "UPLOAD_UNSAFE_PATH"
    assert not (tmp_path.parent / "evil.c").exists()


def test_parallel_read_source_gets_distinct_ids():
    tid = _new_task()
    rec = {"source": "agent", "tool": "read_source", "input": {}, "status": "passed", "started_at": storage.now_iso(),
           "duration_ms": 0, "summary": ""}
    out: list[str] = []
    ts = [threading.Thread(target=lambda: out.append(storage.append_tool_call(tid, rec, True).evidence_ids[0]))
          for _ in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(out, key=lambda s: int(s[1:])) == [f"S{i}" for i in range(1, 21)]
    assert [r.seq for r in storage.read_tool_calls(tid)] == list(range(1, 21))


def test_duplicate_basenames_rejected(client):
    r = client.post("/api/tasks", files=[("files", ("a/main.c", b"int a;", "text/plain")),
                                         ("files", ("b/main.c", b"int b;", "text/plain"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "UPLOAD_BAD_TYPE"


def test_request_invalid_shapes(client):
    r = client.post("/api/tasks/t20990101000000abcdef/start", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REQUEST_INVALID"
    r = client.post("/tools/read_source", headers=TOKEN, json={"task_id": "x", "project_id": "p1", "path": "a.c",
                                                                "start_line": 0})
    assert r.status_code == 200 and r.json()["error"]["code"] == "REQUEST_INVALID"
    r = client.post("/tools/clang_scan", json={"task_id": "x", "project_id": "p1"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOOL_TOKEN_INVALID"


def test_locations_are_validated():
    review = ReviewResult.model_validate(mocks.example("review_result"))
    review.features[0].locations = [CodeLocation(path="does-not-exist.c", line=999)]
    review.innovation.locations = [CodeLocation(path="empty.c", line=1)]
    review.defects[0].path, review.defects[0].line = "empty.c", 1
    lines = {f["path"]: f["lines"] for f in mocks.example("file_list")["files"]} | {"empty.c": 0}
    diff = DiffResult(status="unsupported")
    defects, warnings = pipeline._finalize_defects(storage.new_task_id(), review, lines, diff, mocks.diff,
                                                   None, None, ScanResult(status="passed", mode="full"))
    assert review.features[0].locations == [] and review.innovation.locations == []
    assert len(defects) == len(review.defects) - 1
    assert sum("不存在" in w for w in warnings) >= 3


def test_required_tools_need_successful_read_and_knowledge():
    tid = _new_task()
    base = {"source": "agent", "input": {}, "started_at": storage.now_iso(), "duration_ms": 0, "summary": ""}
    storage.append_tool_call(tid, {**base, "tool": "read_source", "status": "error"})
    storage.append_tool_call(tid, {**base, "tool": "compile_project", "status": "failed"})
    called = pipeline._called_tools(tid)
    assert "read_source" not in called and "compile_project" in called
    proj = Project.model_validate(mocks.example("ingest_result")["projects"][0])
    assert "knowledge" in pipeline.required_tools(proj, None)


def test_dify_deadline_without_newlines():
    """对方一直发数据但不发换行，也要按截止时间停下。"""
    import time

    from app.core.dify_client import DifyClient, DifyError

    class Endless:
        def iter_text(self):
            while True:
                yield "x"

    with pytest.raises(DifyError) as e:
        list(DifyClient(app_key="k")._lines(Endless(), time.monotonic() + 0.2))
    assert e.value.code == "AGENT_TIMEOUT"

    class Two:
        def iter_text(self):
            yield "data: {\"a\"\r\n"
            yield ": 1}\ndata: {}"

    lines = list(DifyClient(app_key="k")._lines(Two(), time.monotonic() + 5))
    assert lines == ['data: {"a"', ': 1}', 'data: {}']


def test_preload_targets_follow_rule():
    """预读顺序：有告警的 → 新增 → 修改；参考代码原样的告警不算；长文件只取前 400 行加告警附近。"""
    from app.schemas import FileChange, FileEntry, Finding
    files = {p: FileEntry(path=p, size=1, lines=n, lang=lang) for p, n, lang in [
        ("src/a.c", 50, "c"), ("src/b.c", 900, "c"), ("src/new.c", 10, "c"), ("src/base.c", 30, "c"),
        ("src/x.h", 20, "h"), ("README.md", 5, "markdown")]}
    diff = DiffResult(status="passed", files=[
        FileChange(path="src/a.c", change="modified"), FileChange(path="src/b.c", change="modified"),
        FileChange(path="src/new.c", change="added"), FileChange(path="src/x.h", change="added"),
        FileChange(path="README.md", change="added"), FileChange(path="src/base.c", change="same")])
    scan = ScanResult(status="passed", mode="full", findings=[
        Finding(evidence_id="C1", checker="c", path="src/b.c", line=700, message="m"),
        Finding(evidence_id="C2", checker="c", path="src/base.c", line=3, message="m", in_baseline_unchanged=True)])
    t = pipeline.preload_targets(files, diff, scan, None)
    assert t == [("src/b.c", 1, 200), ("src/b.c", 201, 400), ("src/b.c", 680, 720),
                 ("README.md", 1, 5), ("src/new.c", 1, 10), ("src/a.c", 1, 50)]
    assert pipeline.preload_targets(files, diff, scan, None) == t  # 同样输入同样结果


def test_clang_location_type_follows_rule():
    """clang 报过的位置，模型换了类型也按映射表改回来。"""
    from app.schemas import Finding
    review = ReviewResult.model_validate(mocks.example("review_result"))
    d = next(x for x in review.defects if x.path == "src/main.c")
    d.type, d.source = "UNCHECKED_RETURN", "llm"
    scan = ScanResult(status="passed", mode="full", findings=[
        Finding(evidence_id="C7", checker="deadcode.DeadStores", path="src/main.c", line=d.line, message="m",
                defect_type="UNUSED")])
    lines = {f["path"]: f["lines"] for f in mocks.example("file_list")["files"]}
    defects, _ = pipeline._finalize_defects(storage.new_task_id(), review, lines, DiffResult(status="unsupported"),
                                            mocks.diff, None, None, scan)
    got = next(x for x in defects if x.path == "src/main.c")
    assert (got.type, got.severity, got.source) == ("UNUSED", "轻微", "clang+llm")


def test_nudge_keeps_first_conclusions(monkeypatch):
    """漏调知识库被提醒后，保留第一次的缺陷和功能判断，只换进新的 knowledge 讲解。"""
    from types import SimpleNamespace
    from app.core.dify_client import ChatResult
    from app.schemas import AgentThought
    tid = _new_task()
    first = mocks.example("review_result")
    second = json.loads(json.dumps(first))
    second["defects"][0]["knowledge"] = "补查后的讲解"
    second["defects"][1]["type"] = "OTHER_NORMAL"
    second["features"][0]["status"] = "none"
    calls: list[str] = []

    class FakeDify:
        def chat(self, text, user, conv="", deadline=None):
            calls.append(text)
            base = {"source": "agent", "input": {}, "status": "passed", "started_at": storage.now_iso(),
                    "duration_ms": 0, "summary": ""}
            if len(calls) == 1:
                for tool in ["compile_project", "clang_scan", "read_source"]:
                    storage.append_tool_call(tid, {**base, "tool": tool})
                return ChatResult(answer=f"```json\n{json.dumps(first)}\n```", conversation_id="c1")
            return ChatResult(answer=json.dumps(second), conversation_id="c1",
                              thoughts=[AgentThought(id="t", position=1, tool="dataset_os", tool_input="信号量")])

    monkeypatch.setattr(pipeline, "DifyClient", FakeDify)
    monkeypatch.setattr(config, "is_mock", lambda m: False)
    proj = Project.model_validate(mocks.example("ingest_result")["projects"][0])
    review, conv, _, _ = pipeline._agent_review(SimpleNamespace(task_id=tid), TaskPaths(tid, "p1"), proj, None, [])
    assert len(calls) == 2 and "已附源码" in calls[0]
    assert review.defects[0].knowledge == "补查后的讲解"
    assert review.defects[1].type == first["defects"][1]["type"]
    assert review.features[0].status == first["features"][0]["status"]


def test_knowledge_found_in_parallel_round():
    """同一轮并行调用时 Dify 把工具名用 ; 拼在一起，里面有知识库也要算调过"""
    from app.schemas import AgentThought
    tid = _new_task()
    pipeline._record_knowledge(tid, [AgentThought(id="t", position=1, tool="clang_scan;dataset_ab_cd", tool_input="{}")])
    assert "knowledge" in pipeline._called_tools(tid)


def test_dify_strip_think():
    """推理模型的 <think> 段不进答案，否则追问会显示思考过程、评测 JSON 可能取错。"""
    from app.core.dify_client import strip_think

    assert strip_think("<think>\n先看 {x}\n</think>\n答案 {\"a\": 1}") == "答案 {\"a\": 1}"
    assert strip_think("没有思考段") == "没有思考段"
