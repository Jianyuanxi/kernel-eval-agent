"""端到端冒烟：上传 → 选工程 → 等评测完成 → 取报告/导出/追问/源码，再测工具接口。
默认全部用假数据（conftest 里 KE_MOCK_MODULES=all），只验证编排和接口形状。"""
import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import config
from app.core import mocks
from app.main import app

TOKEN = {"X-Tool-Token": config.TOOL_TOKEN}


def _zip() -> bytes:
    """按示例 file_list 造一个同结构的假工程（每个文件行数一致、内容是占位），让示例里的缺陷位置都存在"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in mocks.example("file_list")["files"]:
            z.writestr("demo/" + f["path"], "".join(f"/* line {i} */\n" for i in range(1, f["lines"] + 1)))
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def done_task(client):
    r = client.post("/api/tasks", files={"files": ("demo.zip", _zip(), "application/zip")})
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["stage"] == "waiting_select", info
    tid, pid = info["task_id"], info["projects"][0]["project_id"]
    r = client.post(f"/api/tasks/{tid}/start", json={"project_id": pid})
    assert r.status_code == 200, r.text
    for _ in range(100):
        info = client.get(f"/api/tasks/{tid}").json()
        if info["stage"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert info["stage"] == "done", info
    return tid, pid


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_report(client, done_task):
    tid, _ = done_task
    rep = client.get(f"/api/tasks/{tid}/report").json()
    assert rep["score"]["total"] == 79
    assert len(rep["features"]) == 8
    tools = [(c["source"], c["tool"]) for c in rep["tool_calls"]]
    assert ("pipeline", "clang_scan") in tools and ("agent", "read_source") in tools
    assert [d["counted"] for d in rep["defects"]] == [True, True, True, True, False]
    assert rep["warnings"] == []


def test_events_after(client, done_task):
    tid, _ = done_task
    ev = client.get(f"/api/tasks/{tid}/events").json()
    n = len(ev["tool_calls"])
    assert n > 4
    assert client.get(f"/api/tasks/{tid}/events", params={"after": n}).json()["tool_calls"] == []


def test_export(client, done_task):
    tid, _ = done_task
    assert client.get(f"/api/tasks/{tid}/export", params={"format": "md"}).text.startswith("#")
    assert client.get(f"/api/tasks/{tid}/export", params={"format": "json"}).json()["task_id"] == tid


def test_start_twice_conflicts(client, done_task):
    tid, pid = done_task
    r = client.post(f"/api/tasks/{tid}/start", json={"project_id": pid})
    assert r.status_code == 409 and r.json()["error"]["code"] == "TASK_STATE_CONFLICT"


def test_followup_and_source(client, done_task):
    tid, _ = done_task
    r = client.post(f"/api/tasks/{tid}/followup", json={"question": "为什么会越界？", "defect_index": 0})
    assert r.status_code == 200 and r.json()["answer"]
    r = client.get(f"/api/tasks/{tid}/source", params={"path": "src/bsp/vsnprintf_s.c", "start": 335, "end": 355})
    assert r.status_code == 200 and "|" in r.json()["text"]


def test_bad_upload_type(client):
    r = client.post("/api/tasks", files={"files": ("a.txt", b"hi", "text/plain")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UPLOAD_BAD_TYPE"


def test_missing_task(client):
    r = client.get("/api/tasks/t20990101000000abcdef")
    assert r.status_code == 404 and r.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_tools_need_token(client, done_task):
    tid, pid = done_task
    r = client.post("/tools/clang_scan", json={"task_id": tid, "project_id": pid})
    assert r.status_code == 401


@pytest.mark.parametrize("tool", ["list_files", "compile_project", "run_kernel", "clang_scan", "diff_reference"])
def test_tools_return_stored_results(client, done_task, tool):
    tid, pid = done_task
    r = client.post(f"/tools/{tool}", json={"task_id": tid, "project_id": pid}, headers=TOKEN)
    assert r.status_code == 200 and r.json().get("error") is None, r.text
    last = client.get(f"/api/tasks/{tid}/events").json()["tool_calls"][-1]
    assert last["tool"] == tool and last["source"] == "followup"


def test_tool_read_source_assigns_evidence(client, done_task):
    tid, pid = done_task
    r = client.post("/tools/read_source", headers=TOKEN,
                    json={"task_id": tid, "project_id": pid, "path": "src/main.c", "start_line": 1, "end_line": 20})
    assert r.json()["evidence_id"].startswith("S")


def test_tool_wrong_project(client, done_task):
    tid, _ = done_task
    r = client.post("/tools/clang_scan", json={"task_id": tid, "project_id": "p9"}, headers=TOKEN)
    assert r.status_code == 200 and r.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_read_source_limit_only_in_review(client, done_task, monkeypatch):
    """评审阶段读源码到上限后返回 READ_LIMIT；追问（stage=done）不受限"""
    from app.core import storage
    tid, pid = done_task
    used = sum(1 for r in storage.read_tool_calls(tid)
               if r.tool == "read_source" and r.source == "agent" and r.status == "passed")
    monkeypatch.setattr(config, "READ_SOURCE_MAX", used)
    body = {"task_id": tid, "project_id": pid, "path": "src/main.c", "start_line": 1, "end_line": 5}
    info = storage.load_task(tid)
    info.stage = "reviewing"
    storage.save_task(info)
    try:
        r = client.post("/tools/read_source", headers=TOKEN, json=body)
        assert r.status_code == 200 and r.json()["error"]["code"] == "READ_LIMIT"
    finally:
        info.stage = "done"
        storage.save_task(info)
    assert client.post("/tools/read_source", headers=TOKEN, json=body).json()["evidence_id"].startswith("S")
