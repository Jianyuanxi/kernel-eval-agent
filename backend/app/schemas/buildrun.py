"""块 3：沙箱执行、编译、运行"""
from typing import Literal

from pydantic import BaseModel, Field

from .common import ErrorInfo, FeatureId


class ExecResult(BaseModel):
    """run_in_sandbox 的返回值"""
    exit_code: int | None = Field(description="超时被杀时为 None")
    timed_out: bool
    output: str = Field(description="stdout+stderr 合并，超过上限截断")
    output_bytes: int = Field(description="截断前的总字节数")
    truncated: bool
    duration_s: float


class Diagnostic(BaseModel):
    evidence_id: str = Field(description="B1、B2……按出现顺序")
    severity: Literal["warning", "error"]
    path: str = Field(description="相对工程根；链接器等不在工程内的为空串")
    line: int | None = None
    column: int | None = None
    message: str
    in_project: bool = Field(description="路径在工程内（链接器警告等为 false，不计入警告数）")


class BuildResult(BaseModel):
    status: Literal["passed", "failed", "unsupported", "skipped", "error"]
    duration_s: float = 0
    toolchain_rewritten: list[str] = Field([], description="改写了工具链路径的 CMakeLists.txt（相对工程根）")
    warnings: int = Field(0, description="in_project=true 的警告数，评分用这个")
    errors: int = 0
    diagnostics: list[Diagnostic] = Field([], description="最多 100 条")
    artifact: str | None = Field(None, description="相对工作目录的内核镜像路径，如 build/miniEuler")
    has_compile_commands: bool = False
    log_tail: str = Field("", description="构建日志最后 3000 字符")
    log_file: str = Field("", description="相对任务目录的完整日志路径")
    error: ErrorInfo | None = None


RunAnomaly = Literal["NO_OUTPUT", "EXC_STORM", "OUTPUT_TRUNCATED"]


class RunCommand(BaseModel):
    evidence_id: str = Field(description="R2、R3……（R1 是启动输出）")
    command: str
    output: str = Field(description="这条命令之后到下一个提示符之间的输出，最多 4000 字符")


class RunResult(BaseModel):
    status: Literal["passed", "failed", "skipped", "error"] = Field(
        description="passed=启动且无异常刷屏；failed=没输出或异常刷屏；skipped=没编译成功")
    booted: bool = False
    gic_version: int | None = None
    tried_gic: list[int] = []
    window_s: int = 20
    boot_evidence_id: str = "R1"
    boot_output: str = Field("", description="第一个提示符之前（或全部）输出的前 4000 字符")
    shell_prompt: str | None = Field(None, description="识别到的提示符，如 'miniEuler # '")
    commands: list[RunCommand] = []
    feature_hints: list[FeatureId] = Field([], description="从串口输出能直接看出跑通的功能点，仅供智能体参考")
    anomalies: list[RunAnomaly] = []
    output_bytes: int = 0
    duration_s: float = 0
    log_file: str = ""
    error: ErrorInfo | None = None
