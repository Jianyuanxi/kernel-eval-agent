"""块 2：工程处理。下面 5 个函数的签名已冻结，块 1 的编排代码按这个签名调用。

实现要求见 docs/tasks/块2-工程处理.md。
"""
from pathlib import Path

from app.schemas import DiffResult, FileList, IngestResult, Project, SourceSlice


class PathInvalidError(ValueError):
    """路径在工程外、不存在或不是文本文件。块 1 捕获后返回 PATH_INVALID"""


def ingest_upload(task_dir: Path, upload_paths: list[Path], upload_name: str) -> IngestResult:
    """整理上传文件。

    upload_paths：已保存在 task_dir/upload/ 下的文件（一个 zip，或 1–50 个 .c/.h）。
    产出：task_dir/unpacked/（过滤后的全部文件）、task_dir/projects/{project_id}/（每个工程一份拷贝）。
    失败时返回 status="failed" 和 error，不抛异常。
    """
    raise NotImplementedError


def list_files(project_dir: Path, project_id: str) -> FileList:
    raise NotImplementedError


def read_source(project_dir: Path, path: str, start_line: int, end_line: int) -> SourceSlice:
    """返回带行号的源码片段，一次最多 200 行；越界时截到文件末尾。路径非法抛 PathInvalidError"""
    raise NotImplementedError


def diff_reference(project: Project, project_dir: Path, ref_root: Path) -> DiffResult:
    """创新点 C：选文件路径重合最多的参考 lab 作基线（并列取编号大的），归一化换行和行尾空白后逐文件对比"""
    raise NotImplementedError


def change_flags(diff: DiffResult | None, path: str, line: int) -> tuple[bool | None, bool]:
    """给一条缺陷判断 (in_student_change, in_baseline_unchanged)。

    diff 为 None 或 status!="passed" 时返回 (None, False)。
    """
    raise NotImplementedError
