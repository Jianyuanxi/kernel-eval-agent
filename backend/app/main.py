"""后端入口：在 backend/ 目录下运行 uvicorn app.main:app --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import config
from app.core import api, pipeline, storage, tools_api
from app.core.api import ApiError, error_response
from app.core.pipeline import ACTIVE_STAGES, PipelineError
from app.schemas import ErrorInfo


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.TASKS_ROOT.mkdir(parents=True, exist_ok=True)
    # 重启前没跑完的任务标为失败，不自动重跑
    for meta in config.TASKS_ROOT.glob("*/meta.json"):
        info = storage.load_task(meta.parent.name)
        if info and info.stage in ACTIVE_STAGES:
            info.stage, info.progress = "failed", "服务重启，任务中断，请重新上传"
            info.error = ErrorInfo(code="INTERNAL_ERROR", message="服务重启，任务中断")
            storage.save_task(info)
    pipeline.start_worker()
    yield


app = FastAPI(title="内核代码评测智能体", version="0.1.0", lifespan=lifespan)
app.include_router(api.router)
app.include_router(tools_api.router)


@app.exception_handler(ApiError)
def _api_error(request: Request, e: ApiError):
    return error_response(e)


@app.exception_handler(PipelineError)
def _pipeline_error(request: Request, e: PipelineError):
    return error_response(ApiError(500, e.code, str(e)))
