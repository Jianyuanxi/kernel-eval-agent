"""块 2：上传整理、文件清单、读源码、参考代码对比（创新点 C）"""
from typing import Literal

from pydantic import BaseModel, Field

from .common import ErrorInfo, LineRange


class Project(BaseModel):
    project_id: str = Field(description="p1、p2……按工程根目录路径字典序编号")
    name: str = Field(description="工程目录名，如 lab10；工程根就是上传根时用上传文件名去掉扩展名")
    root: str = Field(description="相对解压根目录的路径，/ 分隔；就是根目录时为 .")
    kind: Literal["full", "fragment"] = Field(description="full=有 CMake 工程可编译；fragment=只有零散源文件")
    arch: Literal["aarch64", "riscv64", "unknown"]
    buildable: bool = Field(description="kind=full 且 arch=aarch64 才为 true")
    file_count: int
    c_files: int
    has_run_script: bool = Field(description="工程根下有 runMiniEuler.sh")
    note: str = ""


class IngestResult(BaseModel):
    status: Literal["passed", "failed"]
    upload_name: str
    projects: list[Project] = []
    ignored_count: int = Field(0, description="被过滤掉的文件数（build 产物、.git、__MACOSX 等）")
    error: ErrorInfo | None = None


class FileEntry(BaseModel):
    path: str
    size: int
    lines: int
    lang: Literal["c", "h", "asm", "cmake", "shell", "ld", "markdown", "other"]


class FileList(BaseModel):
    project_id: str
    total: int
    files: list[FileEntry]


class SourceSlice(BaseModel):
    evidence_id: str = Field("", description="S1、S2……由块 1 在工具层分配，模块函数返回空串即可")
    path: str
    start_line: int
    end_line: int
    total_lines: int
    text: str = Field(description='每行格式 f"{行号:>5} | {内容}"，以 \\n 连接')


class FileChange(BaseModel):
    evidence_id: str = Field("", description="D1、D2……只给 modified/added 分配")
    path: str
    change: Literal["same", "modified", "added"]
    added_lines: int = 0
    removed_lines: int = 0
    hunks: list[LineRange] = Field([], description="学生文件里新增或改动的行范围；added 文件就是整个文件")


class DiffResult(BaseModel):
    status: Literal["passed", "unsupported", "error"]
    ref_repo: str = "https://gitee.com/leeboby/os2024_exp_redo_kp"
    ref_commit: str = ""
    baseline: str | None = Field(None, description="选中的参考 lab，如 lab10")
    candidates: dict[str, int] = Field({}, description="各参考 lab 与学生工程的同路径文件数")
    same: int = 0
    modified: int = 0
    added: int = 0
    files: list[FileChange] = []
    note: str = ""
    error: ErrorInfo | None = None
