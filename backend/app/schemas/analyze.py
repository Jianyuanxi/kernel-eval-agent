"""块 4：clang 静态分析"""
from typing import Literal

from pydantic import BaseModel, Field

from .common import DefectType, ErrorInfo, Severity


class Finding(BaseModel):
    evidence_id: str = Field(description="C1、C2……去重后按 (path, line) 排序编号")
    checker: str = Field(description="clang 检查器名，如 core.NullDereference")
    path: str
    line: int
    column: int | None = None
    message: str
    defect_type: DefectType | None = Field(None, description="按 docs/03 的映射表转换，映射不到为 null")
    severity: Severity | None = None
    in_baseline_unchanged: bool | None = Field(
        None, description="所在文件与参考代码完全相同；由块 1 在拿到 DiffResult 后填写")


class FileFailure(BaseModel):
    path: str
    reason: str = Field(description="clang 报错的第一行，如缺少头文件")


class ScanResult(BaseModel):
    status: Literal["passed", "unsupported", "error"] = Field(
        description="passed=至少扫成一个文件；unsupported=一个都没扫成；error=工具自身出错")
    mode: Literal["full", "fragment"]
    target: str = "aarch64-none-elf"
    files_total: int = 0
    files_scanned: int = 0
    files_failed: list[FileFailure] = []
    coverage: float = Field(0, description="files_scanned / files_total，保留两位小数")
    findings_total: int = Field(0, description="去重后总数（findings 最多保留 100 条）")
    findings: list[Finding] = []
    duration_s: float = 0
    log_file: str = ""
    error: ErrorInfo | None = None
