"""给 Dify 调用的工具接口（/tools/*），与 contracts/tools.openapi.yaml 一一对应。

- 只接受 POST + 扁平 JSON，必须带请求头 X-Tool-Token。
- 编译/运行/扫描/对比返回流水线已经存好的结果（重复调用不会重复执行），每次调用都记一条 ToolCallRecord。
- 除令牌错误返回 401 外，出错一律 HTTP 200 + {"error": {...}}，让模型能读到原因。
- 返回给模型的内容要短：列表截断，日志只给尾部。
"""
import time

from fastapi import APIRouter, Depends, Header, HTTPException

from app import config
from app.core import modules, storage
from app.core.storage import TaskPaths, now_iso
from app.schemas import (
    BuildResult, DiffResult, ProjectRef, ReadSourceRequest, RunResult, ScanResult,
)

router = APIRouter(prefix="/tools", tags=["tools"])


def _check_token(x_tool_token: str = Header("")) -> None:
    if x_tool_token != config.TOOL_TOKEN:
        raise HTTPException(401, detail={"error": {"code": "TOOL_TOKEN_INVALID", "message": "工具令牌不对"}})


def _err(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _ctx(ref: ProjectRef):
    info = storage.load_task(ref.task_id)
    if info is None:
        return None, _err("TASK_NOT_FOUND", f"没有任务 {ref.task_id}")
    if ref.project_id != info.selected_project_id:
        return None, _err("PROJECT_NOT_FOUND", f"本任务正在评测的工程是 {info.selected_project_id}")
    return (info, TaskPaths(ref.task_id, ref.project_id)), None


def _log(info, tool: str, inp: dict, status: str, t0: float, summary: str, ev: list[str] | None = None) -> None:
    storage.append_tool_call(info.task_id, {
        "source": "followup" if info.stage == "done" else "agent", "tool": tool, "input": inp,
        "status": status, "started_at": now_iso(), "duration_ms": int((time.monotonic() - t0) * 1000),
        "summary": summary, "evidence_ids": ev or []})


def _stored(ref: ProjectRef, tool: str, name: str, cls, shrink, summarize):
    t0 = time.monotonic()
    ctx, err = _ctx(ref)
    if err:
        return err
    info, paths = ctx
    res = storage.read_model(paths.result(name), cls)
    if res is None:
        _log(info, tool, ref.model_dump(), "error", t0, "结果还没生成")
        return _err("RESULT_NOT_READY", f"{tool} 的结果还没生成（完整工程才有编译和运行结果）")
    out, ev = shrink(res)
    _log(info, tool, ref.model_dump(), res.status, t0, summarize(res), ev)
    return out


@router.post("/list_files", operation_id="list_files", dependencies=[Depends(_check_token)])
def list_files(ref: ProjectRef):
    t0 = time.monotonic()
    ctx, err = _ctx(ref)
    if err:
        return err
    info, paths = ctx
    fl = modules.get("ingest").list_files(paths.project, ref.project_id)
    _log(info, "list_files", ref.model_dump(), "passed", t0, f"共 {fl.total} 个文件")
    d = fl.model_dump()
    d["files"] = d["files"][:300]
    return d


@router.post("/read_source", operation_id="read_source", dependencies=[Depends(_check_token)])
def read_source(req: ReadSourceRequest):
    from app.ingest import PathInvalidError
    t0 = time.monotonic()
    ctx, err = _ctx(req)
    if err:
        return err
    info, paths = ctx
    end = min(req.end_line, req.start_line + 199)
    try:
        s = modules.get("ingest").read_source(paths.project, req.path, req.start_line, end)
    except PathInvalidError as e:
        _log(info, "read_source", req.model_dump(), "error", t0, f"路径无效：{req.path}")
        return _err("PATH_INVALID", str(e))
    n = sum(1 for r in storage.read_tool_calls(info.task_id) if r.tool == "read_source" and r.evidence_ids) + 1
    s.evidence_id = f"S{n}"
    _log(info, "read_source", req.model_dump(), "passed", t0, f"读取 {s.path} 第 {s.start_line}–{s.end_line} 行",
         [s.evidence_id])
    return s.model_dump()


def _shrink_build(b: BuildResult):
    d = b.model_dump(exclude={"log_file"})
    d["diagnostics"] = d["diagnostics"][:30]
    d["log_tail"] = d["log_tail"][-1500:]
    return d, [x["evidence_id"] for x in d["diagnostics"]]


def _shrink_run(r: RunResult):
    d = r.model_dump(exclude={"log_file"})
    return d, [r.boot_evidence_id] + [c.evidence_id for c in r.commands]


def _shrink_scan(s: ScanResult):
    d = s.model_dump(exclude={"log_file"})
    d["findings"] = d["findings"][:50]
    return d, [x["evidence_id"] for x in d["findings"]]


def _shrink_diff(df: DiffResult):
    d = df.model_dump()
    d["files"] = [f for f in d["files"] if f["change"] != "same"][:80]
    return d, [f["evidence_id"] for f in d["files"] if f["evidence_id"]]


@router.post("/compile_project", operation_id="compile_project", dependencies=[Depends(_check_token)])
def compile_project(ref: ProjectRef):
    return _stored(ref, "compile_project", "build", BuildResult, _shrink_build,
                   lambda b: f"编译 {b.status}，{b.warnings} 条警告，{b.errors} 个错误")


@router.post("/run_kernel", operation_id="run_kernel", dependencies=[Depends(_check_token)])
def run_kernel(ref: ProjectRef):
    return _stored(ref, "run_kernel", "run", RunResult, _shrink_run,
                   lambda r: f"运行 {r.status}，{'已启动' if r.booted else '未启动'}，发送 {len(r.commands)} 条命令")


@router.post("/clang_scan", operation_id="clang_scan", dependencies=[Depends(_check_token)])
def clang_scan(ref: ProjectRef):
    return _stored(ref, "clang_scan", "scan", ScanResult, _shrink_scan,
                   lambda s: f"扫描 {s.files_scanned}/{s.files_total} 个文件，{s.findings_total} 条告警")


@router.post("/diff_reference", operation_id="diff_reference", dependencies=[Depends(_check_token)])
def diff_reference(ref: ProjectRef):
    return _stored(ref, "diff_reference", "diff", DiffResult, _shrink_diff,
                   lambda d: f"基线 {d.baseline or '无'}，修改 {d.modified} 个文件，新增 {d.added} 个文件")
