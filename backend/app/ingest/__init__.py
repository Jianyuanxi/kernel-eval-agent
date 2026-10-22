"""块 2：工程处理。下面 5 个函数的签名已冻结，块 1 的编排代码按这个签名调用。

实现要求见 docs/tasks/块2-工程处理.md。
"""
from pathlib import Path

from app.schemas import DiffResult, FileList, IngestResult, Project, SourceSlice


from .source import PathInvalidError, list_files, read_source
from .upload import ingest_upload


def diff_reference(project: Project, project_dir: Path, ref_root: Path) -> DiffResult:
    """创新点 C：选文件路径重合最多的参考 lab 作基线（并列取编号大的），归一化换行和行尾空白后逐文件对比"""
    raise NotImplementedError


def change_flags(diff: DiffResult | None, path: str, line: int) -> tuple[bool | None, bool]:
    """给一条缺陷判断 (in_student_change, in_baseline_unchanged)。

    diff 为 None 或 status!="passed" 时返回 (None, False)。
    """
    raise NotImplementedError
