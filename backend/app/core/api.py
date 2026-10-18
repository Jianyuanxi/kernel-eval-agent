"""给网页用的接口（/api/*），说明见 docs/02-接口规范.md 第 4 节。

出错统一返回 HTTP 4xx/5xx + {"error": {"code", "message"}}。
"""
import shutil

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from app import config
from app.core import modules, pipeline, storage
from app.core.dify_client import DifyClient, DifyError
from app.core.storage import TaskPaths, now_iso
from app.schemas import (
    EventsResponse, FollowupRequest, FollowupResponse, Report, SourceSlice, StartRequest, TaskInfo,
)

router = APIRouter(prefix="/api", tags=["web"])


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def error_response(e: ApiError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"error": {"code": e.code, "message": e.message}})


def _task(task_id: str) -> TaskInfo:
    info = storage.load_task(task_id)
    if info is None:
        raise ApiError(404, "TASK_NOT_FOUND", f"没有任务 {task_id}")
    return info


@router.get("/health")
def health():
    return {"ok": True, "mock_modules": sorted(config.MOCK_MODULES), "sandbox_image": config.SANDBOX_IMAGE}


@router.post("/tasks", response_model=TaskInfo)
def create_task(files: list[UploadFile] = File(...)):
    """上传一个 zip，或 1–50 个 .c/.h 文件"""
    names = [f.filename or "upload" for f in files]
    is_zip = len(files) == 1 and names[0].lower().endswith(".zip")
    if not is_zip and (len(files) > 50 or not all(n.lower().endswith((".c", ".h")) for n in names)):
        raise ApiError(400, "UPLOAD_BAD_TYPE", "只支持一个 .zip，或 1–50 个 .c/.h 文件")
    bases = [n.replace("\\", "/").split("/")[-1] for n in names]
    if len(set(bases)) != len(bases):
        raise ApiError(400, "UPLOAD_BAD_TYPE", "零散上传不支持同名文件，请打成 zip 保留目录结构")
    tid = storage.new_task_id()
    paths = TaskPaths(tid)
    paths.upload.mkdir(parents=True)
    saved, total = [], 0
    for f, n in zip(files, bases):
        dst = paths.upload / n
        with dst.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        total += dst.stat().st_size
        saved.append(dst)
    upload_name = names[0] if is_zip else (names[0] if len(names) == 1 else f"{len(names)} 个源文件")
    info = TaskInfo(task_id=tid, created_at=now_iso(), updated_at=now_iso(), stage="uploaded",
                    progress="正在整理上传文件", upload_name=upload_name)
    if total > config.UPLOAD_MAX_BYTES:
        info.stage, info.progress = "failed", "上传失败"
        info.error = {"code": "UPLOAD_TOO_LARGE", "message": "上传文件超过 20MB"}  # type: ignore[assignment]
        storage.save_task(info)
        return info
    storage.save_task(info)
    res = pipeline._call(modules.get("ingest").ingest_upload, paths.root, saved, upload_name)
    if res.status != "passed":
        info.stage, info.progress, info.error = "failed", "上传文件无法识别", res.error
    else:
        info.projects = res.projects
        info.stage = "waiting_select"
        info.progress = f"识别出 {len(res.projects)} 个工程，请选择要评测的工程"
    storage.save_task(info)
    return info


@router.get("/tasks/{task_id}", response_model=TaskInfo)
def get_task(task_id: str):
    return _task(task_id)


@router.post("/tasks/{task_id}/start", response_model=TaskInfo)
def start_task(task_id: str, req: StartRequest):
    with storage.task_lock(task_id):
        info = _task(task_id)
        if info.stage != "waiting_select":
            raise ApiError(409, "TASK_STATE_CONFLICT", f"任务当前状态是 {info.stage}，不能开始")
        if req.project_id not in {p.project_id for p in info.projects}:
            raise ApiError(404, "PROJECT_NOT_FOUND", f"没有工程 {req.project_id}")
        info.selected_project_id = req.project_id
        info.stage, info.progress = "queued", "排队中"
        storage.save_task(info)
    pipeline.submit(task_id, req.project_id)
    return info


@router.get("/tasks/{task_id}/events", response_model=EventsResponse)
def get_events(task_id: str, after: int = Query(0, ge=0)):
    info = _task(task_id)
    return EventsResponse(stage=info.stage, progress=info.progress, tool_calls=storage.read_tool_calls(task_id, after))


def _report(task_id: str) -> Report:
    info = _task(task_id)
    rep = storage.read_model(TaskPaths(task_id).report, Report) if info.stage == "done" else None
    if rep is None:
        raise ApiError(409, "RESULT_NOT_READY", "报告还没生成")
    return rep


@router.get("/tasks/{task_id}/report", response_model=Report)
def get_report(task_id: str):
    return _report(task_id)


@router.get("/tasks/{task_id}/export")
def export_report(task_id: str, format: str = Query("json", pattern="^(json|md)$")):
    rep = _report(task_id)
    if format == "md":
        text = modules.get("scoring").render_markdown(rep)
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{task_id}.md"'})
    return JSONResponse(rep.model_dump(mode="json"),
                        headers={"Content-Disposition": f'attachment; filename="{task_id}.json"'})


@router.get("/tasks/{task_id}/source", response_model=SourceSlice)
def get_source(task_id: str, path: str, start: int = Query(1, ge=1), end: int = Query(200, ge=1)):
    from app.ingest import PathInvalidError
    info = _task(task_id)
    if not info.selected_project_id:
        raise ApiError(409, "RESULT_NOT_READY", "还没选工程")
    try:
        return modules.get("ingest").read_source(TaskPaths(task_id, info.selected_project_id).project, path,
                                                 start, min(end, start + 199))
    except PathInvalidError as e:
        raise ApiError(400, "PATH_INVALID", str(e))


@router.post("/tasks/{task_id}/followup", response_model=FollowupResponse)
def followup(task_id: str, req: FollowupRequest):
    rep = _report(task_id)
    if req.defect_index is not None and not 0 <= req.defect_index < len(rep.defects):
        raise ApiError(400, "PATH_INVALID", "defect_index 超出范围")
    try:
        return pipeline._call(modules.get("followup").answer_followup, rep, req,
                              DifyClient(timeout_s=config.FOLLOWUP_TIMEOUT_S))
    except DifyError as e:
        raise ApiError(502, e.code, str(e))
    except pipeline.PipelineError as e:
        raise ApiError(500, e.code, str(e))
