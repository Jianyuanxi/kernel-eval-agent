"""参考实验基线选择、文本差异与学生改动标记。"""
import difflib
import re
from pathlib import Path

from app import config
from app.schemas import DiffResult, Project
from app.schemas.common import ErrorInfo, LineRange
from app.schemas.ingest import FileChange
from .source import PathInvalidError, project_files


def _normalized_lines(path: Path) -> list[str] | None:
    """拒绝含 NUL 的二进制内容，归一化文本并去掉末尾空行。"""
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    lines = [line.replace("\r", "").rstrip() for line in data.decode("utf-8", errors="replace").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def diff_reference(project: Project, project_dir: Path, ref_root: Path) -> DiffResult:
    """选择同路径最多的参考 lab，返回学生侧变更行与稳定证据编号。"""
    result = DiffResult(status="unsupported", ref_commit=config.REF_COMMIT)
    try:
        if not ref_root.is_dir():
            result.note = "参考代码目录不存在"
            return result
        labs = sorted((p for p in ref_root.iterdir() if p.is_dir() and re.fullmatch(r"lab\d+", p.name)),
                      key=lambda p: (int(p.name[3:]), p.name))
        if not labs:
            result.note = "参考代码目录下没有 lab 实验目录"
            return result
        if not project_dir.is_dir():
            raise PathInvalidError("工程目录不存在")
        student_files = {p.relative_to(project_dir).as_posix(): p for p in project_files(project_dir)}
        references = {}
        for lab in labs:
            if lab.is_symlink() or not lab.resolve().is_relative_to(ref_root.resolve()):
                raise PathInvalidError("参考实验目录越界")
            references[lab.name] = {p.relative_to(lab).as_posix(): p for p in project_files(lab)}
        result.candidates = {lab.name: len(student_files.keys() & references[lab.name].keys()) for lab in labs}
        baseline = max(result.candidates, key=lambda name: (result.candidates[name], int(name[3:]), name))
        if result.candidates[baseline] == 0:
            result.note = "学生工程与参考实验没有相同路径的文件"
            return result
        result.baseline = baseline
        skipped = 0
        changes = []
        evidence = 0
        for name, path in student_files.items():
            student = _normalized_lines(path)
            reference_path = references[baseline].get(name)
            reference = _normalized_lines(reference_path) if reference_path is not None else []
            if student is None or reference is None:
                skipped += 1
                continue
            change = FileChange(path=name, change="same")
            if reference_path is None:
                change.change = "added"
                change.added_lines = len(student)
                if student:
                    change.hunks = [LineRange(start=1, end=len(student))]
            elif student != reference:
                change.change = "modified"
                for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, reference, student, autojunk=False).get_opcodes():
                    if tag in {"replace", "insert"}:
                        change.hunks.append(LineRange(start=j1 + 1, end=j2))
                        change.added_lines += j2 - j1
                    if tag in {"replace", "delete"}:
                        change.removed_lines += i2 - i1
            if change.change != "same":
                evidence += 1
                change.evidence_id = f"D{evidence}"
            changes.append(change)
        result.status = "passed"
        result.files = changes
        result.same = sum(f.change == "same" for f in changes)
        result.modified = sum(f.change == "modified" for f in changes)
        result.added = sum(f.change == "added" for f in changes)
        if skipped:
            result.note = f"已跳过 {skipped} 个学生侧或参考侧含 NUL 的二进制文件，不判断其改动"
        return result
    except (OSError, PathInvalidError):
        return DiffResult(status="error", ref_commit=config.REF_COMMIT,
                          error=ErrorInfo(code="INTERNAL_ERROR", message="无法安全读取工程或参考代码"))


def change_flags(diff: DiffResult | None, path: str, line: int) -> tuple[bool | None, bool]:
    """按文件状态和学生侧闭区间返回改动标记与基线未变标记。"""
    if diff is None or diff.status != "passed":
        return None, False
    for file in diff.files:
        if file.path == path:
            if file.change == "same":
                return False, True
            return any(hunk.start <= line <= hunk.end for hunk in file.hunks), False
    return None, False
