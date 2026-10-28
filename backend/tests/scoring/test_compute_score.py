"""块 6 阶段 1：compute_score 必须与 docs/03 和示例完全一致。"""
import json

from app.config import EXAMPLES_DIR
from app.schemas import BuildResult, Project, Report, ReportDefect, ReviewResult, RunResult, ScoreResult
from app.scoring import compute_score
from app.scoring.compute import grade_of, percent_total


def _load(name: str):
    return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _sample1():
    """样例 1：contracts/examples 里的工程、编译、运行、评审和报告缺陷。"""
    project = Project.model_validate(_load("ingest_result")["projects"][0])
    build = BuildResult.model_validate(_load("build_result"))
    run = RunResult.model_validate(_load("run_result"))
    review = ReviewResult.model_validate(_load("review_result"))
    defects = [ReportDefect.model_validate(d) for d in _load("report")["defects"]]
    return project, build, run, review, defects


def _copy_defects(defects: list[ReportDefect]) -> list[ReportDefect]:
    return [d.model_copy(deep=True) for d in defects]


def test_sample1_matches_score_result_json():
    """样例 1 与 score_result.json 完全一致：79 中等、raw_total 78.5、4 条扣分。"""
    project, build, run, review, defects = _sample1()
    got = compute_score(project, build, run, review, defects)
    expected = ScoreResult.model_validate(_load("score_result"))
    assert got.model_dump() == expected.model_dump()
    assert got.total == 79 and got.grade == "中等" and got.raw_total == 78.5
    assert len(got.deductions) == 4
    assert [d.counted for d in defects] == [True, True, True, True, False]


def test_build_failed_zeros_compile_and_features():
    project, build, run, review, defects = _sample1()
    build = build.model_copy(update={"status": "failed"})
    got = compute_score(project, build, run, review, _copy_defects(defects))
    items = {i.key: i for i in got.items}
    assert items["compile_run"].score == 0
    assert items["features"].score == 0
    assert "编译不通过" in items["features"].reasons[0]


def test_build_error_excludes_compile_run():
    project, build, run, review, defects = _sample1()
    build = build.model_copy(update={"status": "error"})
    got = compute_score(project, build, run, review, _copy_defects(defects))
    items = {i.key: i for i in got.items}
    assert items["compile_run"].score is None
    assert items["compile_run"].reasons == ["评测工具出错，本项不计分"]
    counted = [i for i in got.items if i.score is not None]
    assert sum(i.max for i in counted) == 80
    assert got.total == percent_total(got.raw_total, 80)


def test_fragment_excludes_compile_run():
    project, _, _, review, defects = _sample1()
    project = project.model_copy(update={"buildable": False, "kind": "fragment"})
    got = compute_score(project, None, None, review, _copy_defects(defects))
    items = {i.key: i for i in got.items}
    assert got.mode == "fragment"
    assert items["compile_run"].score is None
    assert items["compile_run"].reasons == ["只提交了代码片段，不评编译与运行"]
    assert sum(i.max for i in got.items if i.score is not None) == 80
    assert got.total == percent_total(got.raw_total, 80)


def test_warning_penalty_brackets():
    """警告 0 / 1 / 10 / 11 条时编译分为 10 / 9 / 9 / 8（另加运行 10 分）。"""
    project, build, run, review, defects = _sample1()
    expected = {0: 20.0, 1: 19.0, 10: 19.0, 11: 18.0}
    compile_part = {0: 10, 1: 9, 10: 9, 11: 8}
    for n, total in expected.items():
        b = build.model_copy(update={"warnings": n})
        got = compute_score(project, b, run, review, _copy_defects(defects))
        cr = next(i for i in got.items if i.key == "compile_run")
        assert cr.score == total, n
        assert cr.score - 10 == compile_part[n]


def test_reliability_floors_at_zero():
    project, build, run, review, defects = _sample1()
    extra = []
    template = defects[0].model_copy(update={"in_baseline_unchanged": False})
    for _ in range(8):
        extra.append(template.model_copy(deep=True))
    all_defects = extra  # 8 个严重 = 40 分，应扣到 0
    got = compute_score(project, build, run, review, all_defects)
    rel = next(i for i in got.items if i.key == "reliability")
    assert rel.score == 0
    assert all(d.counted for d in all_defects)


def test_all_baseline_unchanged_not_counted():
    project, build, run, review, defects = _sample1()
    for d in defects:
        d.in_baseline_unchanged = True
    got = compute_score(project, build, run, review, defects)
    rel = next(i for i in got.items if i.key == "reliability")
    assert rel.score == 25
    assert got.deductions == []
    assert all(d.counted is False for d in defects)
    assert "参考代码原有的 5 个问题不扣分" in rel.reasons


def test_rounding_boundaries():
    """int(x + 0.5)：89.5→90、90→90、79.99→80，等级对应。"""
    assert percent_total(89.5, 100) == 90
    assert percent_total(90, 100) == 90
    assert percent_total(79.99, 100) == 80
    assert grade_of(90) == "优秀"
    assert grade_of(80) == "良好"
    assert grade_of(79) == "中等"

    project, build, run, review, defects = _sample1()
    # 20 + 37.5 + 17 + 15 = 89.5 → 90 优秀
    b = build.model_copy(update={"warnings": 0})
    style = review.style.model_copy(update={"grade": "good"})
    review_good = review.model_copy(update={"style": style})
    kept = [defects[0].model_copy(deep=True), defects[2].model_copy(deep=True), defects[3].model_copy(deep=True)]
    got = compute_score(project, b, run, review_good, kept)
    assert got.raw_total == 89.5
    assert got.total == 90 and got.grade == "优秀"

    # 20 + 40 + 15 + 15 = 90 → 90 优秀
    all_done = [f.model_copy(update={"status": "done"}) for f in review.features]
    review_full = review.model_copy(update={"features": all_done, "style": style})
    two_severe = [defects[0].model_copy(deep=True), defects[1].model_copy(deep=True)]
    got90 = compute_score(project, b, run, review_full, two_severe)
    assert got90.raw_total == 90
    assert got90.total == 90 and got90.grade == "优秀"


def test_same_input_twice():
    project, build, run, review, defects = _sample1()
    a = compute_score(project, build, run, review, _copy_defects(defects))
    b = compute_score(project, build, run, review, _copy_defects(defects))
    assert a.model_dump() == b.model_dump()


def test_report_example_defects_match_pipeline_shape():
    """用报告示例整包再算一遍，分数仍与 score_result 一致。"""
    report = Report.model_validate(_load("report"))
    got = compute_score(report.project, report.build, report.run, ReviewResult.model_validate(_load("review_result")),
                        report.defects)
    assert got == ScoreResult.model_validate(_load("score_result"))
