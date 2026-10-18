"""块 1：任务状态、工具调用记录、最终报告、前端接口"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from .analyze import ScanResult
from .buildrun import BuildResult, RunResult
from .common import ErrorInfo, Status
from .ingest import DiffResult, Project
from .review import FeatureJudgement, InnovationJudgement, ReportDefect, StyleJudgement
from .score import ScoreResult

TaskStage = Literal[
    "uploaded",        # 刚收到文件
    "waiting_select",  # 整理完，等用户选工程（只有一个工程时前端自动选）
    "queued",
    "building", "running", "scanning", "diffing", "reviewing", "scoring",
    "done", "failed",
]


class TaskInfo(BaseModel):
    task_id: str = Field(description='"t" + yyyymmddHHMMSS + 6 位随机十六进制，如 t20261020153000a1b2c3')
    created_at: str = Field(description="ISO 8601，带时区")
    updated_at: str
    stage: TaskStage
    progress: str = Field("", description="给人看的当前进度，如“正在 QEMU 中运行内核”")
    upload_name: str
    projects: list[Project] = []
    selected_project_id: str | None = None
    error: ErrorInfo | None = None


class StartRequest(BaseModel):
    project_id: str


class ToolCallRecord(BaseModel):
    seq: int = Field(description="任务内从 1 递增")
    source: Literal["pipeline", "agent", "followup"]
    tool: str = Field(description="list_files / read_source / compile_project / run_kernel / clang_scan / diff_reference / knowledge")
    input: dict[str, Any] = {}
    status: Status
    started_at: str
    duration_ms: int
    summary: str = Field(description="一句话结果，如“编译通过，2 条警告”")
    evidence_ids: list[str] = []


class AgentThought(BaseModel):
    """Dify agent_thought 事件按 id 合并后的结果"""
    id: str
    position: int
    thought: str = ""
    tool: str = ""
    tool_input: str = ""
    observation: str = Field("", description="最多 2000 字符")


class Report(BaseModel):
    task_id: str
    generated_at: str
    project: Project
    mode: Literal["full", "fragment"]
    build: BuildResult | None
    run: RunResult | None
    scan: ScanResult
    diff: DiffResult | None
    summary: str
    features: list[FeatureJudgement]
    defects: list[ReportDefect]
    style: StyleJudgement
    innovation: InnovationJudgement
    score: ScoreResult
    tool_calls: list[ToolCallRecord]
    agent_thoughts: list[AgentThought] = []
    model: str = Field("", description="实际使用的模型 ID")
    conversation_id: str = Field("", description="Dify 会话 ID，追问时复用")
    warnings: list[str] = Field([], description="例如“丢弃了 2 条行号不存在的缺陷”")


class FollowupRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    defect_index: int | None = Field(None, description="针对某条缺陷追问时填 Report.defects 下标")


class FollowupResponse(BaseModel):
    answer: str = Field(description="Markdown 文本")
    tool_calls: list[ToolCallRecord] = []


class EventsResponse(BaseModel):
    """GET /api/tasks/{id}/events?after=N 的返回：seq > N 的工具调用记录"""
    stage: TaskStage
    progress: str
    tool_calls: list[ToolCallRecord]
