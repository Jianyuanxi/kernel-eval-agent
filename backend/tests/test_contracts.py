"""契约检查：contracts/examples 里每个示例都必须能被对应 schema 解析，且彼此一致。
改了 schemas 或示例后必须跑通这个文件。"""
import json

import pytest

from app import config
from app.core.pipeline import parse_review
from app.schemas import (
    DEFECT_TYPES, BuildResult, DiffResult, FileList, FollowupResponse, IngestResult, Report, ReviewResult,
    RunResult, ScanResult, ScoreResult, SourceSlice,
)

EXAMPLES = {
    "ingest_result": IngestResult, "file_list": FileList, "source_slice": SourceSlice, "build_result": BuildResult,
    "run_result": RunResult, "scan_result": ScanResult, "diff_result": DiffResult, "review_result": ReviewResult,
    "score_result": ScoreResult, "report": Report, "followup_response": FollowupResponse,
}


def load(name):
    return json.loads((config.EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_validates(name):
    EXAMPLES[name].model_validate(load(name))


def test_no_extra_example_files():
    assert {p.stem for p in config.EXAMPLES_DIR.glob("*.json")} == set(EXAMPLES)


def test_report_consistent_with_parts():
    rep = Report.model_validate(load("report"))
    assert rep.score == ScoreResult.model_validate(load("score_result"))
    assert rep.build == BuildResult.model_validate(load("build_result"))
    assert rep.scan == ScanResult.model_validate(load("scan_result"))
    review = ReviewResult.model_validate(load("review_result"))
    assert [d.title for d in rep.defects] == [d.title for d in review.defects]
    for d in rep.defects:
        name, sev, kc = DEFECT_TYPES[d.type]
        assert (d.type_name, d.severity, d.knowledge_category) == (name, sev, kc)
    assert sum(x.points for x in rep.score.deductions) == 25 - next(
        i.score for i in rep.score.items if i.key == "reliability")


def test_score_total_rounding():
    s = ScoreResult.model_validate(load("score_result"))
    assert s.raw_total == sum(i.score for i in s.items if i.score is not None)
    assert s.total == int(s.raw_total + 0.5)


def test_parse_review_accepts_fenced_and_bare_json():
    text = json.dumps(load("review_result"), ensure_ascii=False)
    assert parse_review(f"好的，结果如下：\n```json\n{text}\n```").summary
    assert parse_review(text).summary
    with pytest.raises(ValueError):
        parse_review("我没有输出 JSON")
