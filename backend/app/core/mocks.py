"""假数据实现：用 contracts/examples/ 里的固定 JSON 顶替还没做好的模块（KE_MOCK_MODULES 控制）。

每个命名空间的函数签名和真实模块完全一致，这样切换时编排代码不用改。
"""
import json
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.config import EXAMPLES_DIR, UNPACK_MAX_BYTES, UNPACK_MAX_FILES
from app.schemas import (
    BuildResult, DiffResult, FileList, FollowupResponse, IngestResult, Report, ReviewResult, RunResult,
    ScanResult, ScoreResult, SourceSlice,
)


def example(name: str):
    return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _inside(base: Path, rel: str) -> Path | None:
    """rel 拼到 base 下并 resolve，落在 base 之外（绝对路径、..、盘符）返回 None"""
    if not rel or rel.startswith(("/", "\\")) or ":" in rel:
        return None
    p = (base / rel.replace("\\", "/")).resolve()
    return p if p.is_relative_to(base.resolve()) else None


def _ingest_upload(task_dir: Path, upload_paths: list[Path], upload_name: str) -> IngestResult:
    """工程信息固定用示例；但会把上传内容粗略放进 projects/p1/，这样上传样例 1 时智能体能读到真实源码。
    不做过滤和工程识别（那是块 2 的活），只在开发期用；但路径越界和解压上限是真检查（公网部署也跑这段）。"""
    r = IngestResult.model_validate(example("ingest_result"))
    r.upload_name = upload_name
    dst = task_dir / "projects" / r.projects[0].project_id
    dst.mkdir(parents=True, exist_ok=True)

    def fail(code: str, msg: str) -> IngestResult:
        return IngestResult(status="failed", upload_name=upload_name, error={"code": code, "message": msg})

    for up in upload_paths:
        if up.suffix.lower() != ".zip":
            shutil.copy(up, dst / up.name)
            continue
        try:
            with zipfile.ZipFile(up) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if len(infos) > UNPACK_MAX_FILES:
                    return fail("UPLOAD_TOO_LARGE", f"zip 里超过 {UNPACK_MAX_FILES} 个文件")
                tops = {i.filename.split("/")[0] for i in infos}
                strip = len(tops) == 1 and all("/" in i.filename for i in infos)
                total = 0
                for i in infos:
                    rel = i.filename.split("/", 1)[1] if strip else i.filename
                    out = _inside(dst, rel)
                    if out is None or (i.external_attr >> 16) & 0o170000 == 0o120000:  # 越界或符号链接
                        return fail("UPLOAD_UNSAFE_PATH", f"zip 里有不安全的路径：{i.filename}")
                    total += i.file_size  # zipfile 读到声明的大小就停，所以先按声明累计
                    if total > UNPACK_MAX_BYTES:
                        return fail("UPLOAD_TOO_LARGE", "解压后超过 100MB")
                    data = z.read(i)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
        except (zipfile.BadZipFile, RuntimeError) as e:  # RuntimeError：加密 zip
            return fail("UPLOAD_BAD_ZIP", f"zip 损坏或加密：{e}")
    return r


def _lines(p: Path) -> list[str]:
    """按 docs/02 第 1 节的行数规则：\\r\\n 算一个换行，最后一行没换行也算，空文件 0 行"""
    text = p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") or not text else lines


def _list_files(project_dir: Path, project_id: str) -> FileList:
    files = sorted(p for p in project_dir.rglob("*") if p.is_file()) if project_dir.exists() else []
    if not files:
        return FileList.model_validate(example("file_list"))
    lang = {".c": "c", ".h": "h", ".s": "asm", ".ld": "ld", ".sh": "shell", ".md": "markdown"}
    return FileList(project_id=project_id, total=len(files), files=[
        {"path": p.relative_to(project_dir).as_posix(), "size": p.stat().st_size, "lines": len(_lines(p)),
         "lang": "cmake" if p.name == "CMakeLists.txt" else lang.get(p.suffix.lower(), "other")} for p in files])


def _read_source(project_dir: Path, path: str, start_line: int, end_line: int) -> SourceSlice:
    """越界、不存在、二进制都抛 PathInvalidError（和块 2 的真实实现一致）"""
    from app.ingest import PathInvalidError
    f = _inside(project_dir, path)
    if f is None or not f.is_file():
        raise PathInvalidError(f"工程里没有文件 {path}")
    if b"\x00" in f.read_bytes():
        raise PathInvalidError(f"{path} 不是文本文件")
    lines = _lines(f)
    start_line = max(start_line, 1)
    if start_line > len(lines):
        raise PathInvalidError(f"{path} 只有 {len(lines)} 行")
    end = min(end_line, len(lines), start_line + 199)
    return SourceSlice(path=path, start_line=start_line, end_line=end, total_lines=len(lines),
                       text="\n".join(f"{i:>5} | {lines[i - 1]}" for i in range(start_line, end + 1)))


def _change_flags(diff, path: str, line: int):
    if diff is None or diff.status != "passed":
        return None, False
    for f in diff.files:
        if f.path == path:
            if f.change == "same":
                return False, True
            return any(h.start <= line <= h.end for h in f.hunks), False
    return None, False


def _compute_score(project, build, run, review, defects) -> ScoreResult:
    s = ScoreResult.model_validate(example("score_result"))
    counted = {d.defect_index for d in s.deductions}
    for i, d in enumerate(defects):
        d.counted = i in counted
    return s


def _render_markdown(report: Report) -> str:
    return f"# 评测报告（假数据）\n\n总分 {report.score.total}，{report.score.grade}\n\n{report.summary}\n"


ingest = SimpleNamespace(
    ingest_upload=_ingest_upload,
    list_files=_list_files,
    read_source=_read_source,
)
diff = SimpleNamespace(
    diff_reference=lambda project, project_dir, ref_root: DiffResult.model_validate(example("diff_result")),
    change_flags=_change_flags,
)
buildrun = SimpleNamespace(
    build=lambda project, project_dir, work_dir, log_dir: BuildResult.model_validate(example("build_result")),
    run=lambda project, work_dir, build_result, log_dir: RunResult.model_validate(example("run_result")),
)
analyze = SimpleNamespace(
    scan=lambda project, project_dir, work_dir, log_dir: ScanResult.model_validate(example("scan_result")),
)
scoring = SimpleNamespace(compute_score=_compute_score, render_markdown=_render_markdown)
followup = SimpleNamespace(
    answer_followup=lambda report, req, dify: FollowupResponse.model_validate(example("followup_response")),
)


def review() -> ReviewResult:
    return ReviewResult.model_validate(example("review_result"))


def agent_tool_calls() -> list[dict]:
    """假智能体“调用过”的工具（取自示例报告里 source=agent 的记录，不含 seq）"""
    out = []
    for r in example("report")["tool_calls"]:
        if r["source"] == "agent":
            r = dict(r)
            r.pop("seq")
            out.append(r)
    return out
