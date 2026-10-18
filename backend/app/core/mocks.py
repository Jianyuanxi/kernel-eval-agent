"""假数据实现：用 contracts/examples/ 里的固定 JSON 顶替还没做好的模块（KE_MOCK_MODULES 控制）。

每个命名空间的函数签名和真实模块完全一致，这样切换时编排代码不用改。
"""
import json
from pathlib import Path
from types import SimpleNamespace

from app.config import EXAMPLES_DIR
from app.schemas import (
    BuildResult, DiffResult, FileList, FollowupResponse, IngestResult, Report, ReviewResult, RunResult,
    ScanResult, ScoreResult, SourceSlice,
)


def example(name: str):
    return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _ingest_upload(task_dir: Path, upload_paths: list[Path], upload_name: str) -> IngestResult:
    r = IngestResult.model_validate(example("ingest_result"))
    r.upload_name = upload_name
    for p in r.projects:
        (task_dir / "projects" / p.project_id).mkdir(parents=True, exist_ok=True)
    return r


def _read_source(project_dir: Path, path: str, start_line: int, end_line: int) -> SourceSlice:
    s = SourceSlice.model_validate(example("source_slice"))
    s.path = path
    return s


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
    list_files=lambda project_dir, project_id: FileList.model_validate(example("file_list")),
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
