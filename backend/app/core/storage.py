"""任务目录与 JSON 存取。目录结构见 docs/02-接口规范.md 第 3 节。"""
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.config import TASKS_ROOT
from app.schemas import TaskInfo, ToolCallRecord

M = TypeVar("M", bound=BaseModel)
_TASK_ID = re.compile(r"^t\d{14}[0-9a-f]{6}$")
_PROJECT_ID = re.compile(r"^p\d{1,3}$")
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
CST = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def new_task_id() -> str:
    return "t" + datetime.now(CST).strftime("%Y%m%d%H%M%S") + secrets.token_hex(3)


def valid_task_id(task_id: str) -> bool:
    return bool(_TASK_ID.match(task_id))


def valid_project_id(project_id: str) -> bool:
    return bool(_PROJECT_ID.match(project_id))


def task_lock(task_id: str) -> threading.RLock:
    """同一任务的元数据和工具记录读写都在这把锁里；可重入，同一线程嵌套加锁不会卡死"""
    with _locks_guard:
        return _locks.setdefault(task_id, threading.RLock())


class TaskPaths:
    """一个任务（和其中一个工程）用到的所有路径"""

    def __init__(self, task_id: str, project_id: str | None = None):
        self.task_id = task_id
        self.root = TASKS_ROOT / task_id
        self.meta = self.root / "meta.json"
        self.upload = self.root / "upload"
        self.tool_calls = self.root / "tool_calls.jsonl"
        self.report = self.root / "report.json"
        self.pid = project_id
        if project_id:
            self.project = self.root / "projects" / project_id
            self.results = self.root / "results" / project_id
            self.work_build = self.root / "work" / project_id / "build"
            self.work_scan = self.root / "work" / project_id / "scan"
            self.logs = self.root / "logs" / project_id

    def result(self, name: str) -> Path:
        """name: build / run / scan / diff / review / score"""
        return self.results / f"{name}.json"

    def rel(self, p: str | Path) -> str:
        """把绝对路径转成相对任务目录的路径（写进报告用）"""
        try:
            return Path(p).resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(p)


def _retry(fn):
    """Windows 上文件正被另一线程读写时 replace/open 会报 PermissionError，短暂重试即可（Linux 不会触发）"""
    for _ in range(50):
        try:
            return fn()
        except PermissionError:
            time.sleep(0.02)
    return fn()


def write_json(path: Path, data: BaseModel | dict | list) -> None:
    """原子写入：先写临时文件再改名，避免读到半个文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data.model_dump_json(indent=2) if isinstance(data, BaseModel) else json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + f".{secrets.token_hex(3)}.tmp")
    tmp.write_text(text, encoding="utf-8")
    _retry(lambda: os.replace(tmp, path))


def read_model(path: Path, cls: type[M]) -> M | None:
    if not path.exists():
        return None
    return cls.model_validate_json(_retry(lambda: path.read_text(encoding="utf-8")))


def load_task(task_id: str) -> TaskInfo | None:
    if not valid_task_id(task_id):
        return None
    return read_model(TaskPaths(task_id).meta, TaskInfo)


def save_task(info: TaskInfo) -> None:
    info.updated_at = now_iso()
    write_json(TaskPaths(info.task_id).meta, info)


def append_tool_call(task_id: str, rec: dict, new_source_evidence: bool = False) -> ToolCallRecord:
    """追加一条工具调用记录，seq 自动编号。rec 不含 seq。

    new_source_evidence=True 时在同一把锁里分配下一个 S 编号写进 evidence_ids（read_source 用，并行调用也不会撞号）。
    """
    p = TaskPaths(task_id).tool_calls
    with task_lock(task_id):
        old = read_tool_calls(task_id)
        if new_source_evidence:
            n = sum(1 for r in old if r.tool == "read_source" and r.evidence_ids) + 1
            rec = {**rec, "evidence_ids": [f"S{n}"]}
        r = ToolCallRecord(seq=len(old) + 1, **rec)
        with p.open("a", encoding="utf-8") as f:
            f.write(r.model_dump_json() + "\n")
    return r


def read_tool_calls(task_id: str, after: int = 0) -> list[ToolCallRecord]:
    p = TaskPaths(task_id).tool_calls
    with task_lock(task_id):  # 和追加互斥，不会读到写了一半的行
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if line.strip():
            r = ToolCallRecord.model_validate_json(line)
            if r.seq > after:
                out.append(r)
    return out
