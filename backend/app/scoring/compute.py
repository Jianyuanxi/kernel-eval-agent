"""按 docs/03 计算四项分数与百分制总分。"""
from app.schemas import (
    FEATURE_NAMES,
    SEVERITY_PENALTY,
    BuildResult,
    Deduction,
    Project,
    ReportDefect,
    ReviewResult,
    RunResult,
    ScoreItem,
    ScoreResult,
)

_STYLE_LABEL = {"good": "好", "medium": "中", "poor": "差"}
_STYLE_SCORE = {"good": 15.0, "medium": 10.0, "poor": 5.0}
_FEATURE_SCORE = {"done": 5.0, "partial": 2.5, "none": 0.0}
_ITEM_META = (
    ("compile_run", "编译与运行", 20.0),
    ("features", "功能完成度", 40.0),
    ("reliability", "代码可靠性", 25.0),
    ("style", "规范与可读性", 15.0),
)
_GRADE = (
    (90, "优秀"),
    (80, "良好"),
    (70, "中等"),
    (60, "及格"),
)


def percent_total(raw_total: float, max_sum: float) -> int:
    """百分制总分：int(raw / 满分之和 × 100 + 0.5)，不用 round()。"""
    return int(raw_total / max_sum * 100 + 0.5)


def grade_of(total: int) -> str:
    """按百分制总分定等级。"""
    for threshold, name in _GRADE:
        if total >= threshold:
            return name
    return "不及格"


def warning_penalty(warnings: int) -> int:
    """工程内警告：0 条不扣，1–10 条扣 1，超过 10 条扣 2。"""
    if warnings <= 0:
        return 0
    if warnings <= 10:
        return 1
    return 2


def _compile_run(project: Project, build: BuildResult | None, run: RunResult | None) -> tuple[float | None, list[str]]:
    if not project.buildable:
        return None, ["只提交了代码片段，不评编译与运行"]
    if (build is not None and build.status == "error") or (run is not None and run.status == "error"):
        return None, ["评测工具出错，本项不计分"]
    if build is None or build.status != "passed":
        return 0.0, ["编译失败，编译与运行记 0 分"]
    penalty = warning_penalty(build.warnings)
    compile_score = 10 - penalty
    if penalty == 0:
        reasons = ["编译通过，无警告不扣分"]
    else:
        reasons = [f"编译通过，{build.warnings} 条警告扣 {penalty} 分"]
    run_score = 10.0 if run is not None and run.status == "passed" else 0.0
    if run_score:
        reasons.append("QEMU 中正常启动")
    else:
        reasons.append("未能在 QEMU 中正常启动，运行分 0 分")
    return float(compile_score + run_score), reasons


def _features(project: Project, build: BuildResult | None, review: ReviewResult) -> tuple[float, list[str]]:
    if project.buildable and build is not None and build.status == "failed":
        return 0.0, ["编译不通过，按评分表本项记 0 分"]
    groups: dict[str, list[str]] = {"done": [], "partial": [], "none": []}
    total = 0.0
    for f in review.features:
        groups[f.status].append(FEATURE_NAMES[f.feature_id])
        total += _FEATURE_SCORE[f.status]
    parts: list[str] = []
    if groups["done"]:
        parts.append(f"完成 {len(groups['done'])} 项")
    if groups["partial"]:
        parts.append(f"部分完成 {len(groups['partial'])} 项（{'、'.join(groups['partial'])}）")
    if groups["none"]:
        parts.append(f"未完成 {len(groups['none'])} 项（{'、'.join(groups['none'])}）")
    return total, ["，".join(parts) if parts else "未给出功能点判断"]


def _reliability(defects: list[ReportDefect]) -> tuple[float, list[str], list[Deduction]]:
    deductions: list[Deduction] = []
    counts = {"严重": 0, "一般": 0, "轻微": 0}
    points = {"严重": 0, "一般": 0, "轻微": 0}
    skipped = 0
    deducted = 0
    for i, d in enumerate(defects):
        if d.in_baseline_unchanged:
            d.counted = False
            skipped += 1
            continue
        d.counted = True
        p = SEVERITY_PENALTY[d.severity]
        deductions.append(Deduction(defect_index=i, type=d.type, severity=d.severity, points=p))
        counts[d.severity] += 1
        points[d.severity] += p
        deducted += p
    score = max(0.0, 25.0 - deducted)
    reasons = [f"{sev} {counts[sev]} 个扣 {points[sev]} 分" for sev in ("严重", "一般", "轻微") if counts[sev]]
    if skipped:
        reasons.append(f"参考代码原有的 {skipped} 个问题不扣分")
    if not reasons:
        reasons.append("未发现问题")
    return score, reasons, deductions


def compute_score(project: Project, build: BuildResult | None, run: RunResult | None,
                  review: ReviewResult, defects: list[ReportDefect]) -> ScoreResult:
    """按 docs/03 计算分数，并就地填写 defects[i].counted。"""
    mode = "full" if project.buildable else "fragment"
    cr_score, cr_reasons = _compile_run(project, build, run)
    feat_score, feat_reasons = _features(project, build, review)
    rel_score, rel_reasons, deductions = _reliability(defects)
    style_score = _STYLE_SCORE[review.style.grade]
    style_reasons = [f"{_STYLE_LABEL[review.style.grade]}：{review.style.reason}"]
    scores = {
        "compile_run": cr_score,
        "features": feat_score,
        "reliability": rel_score,
        "style": style_score,
    }
    reasons = {
        "compile_run": cr_reasons,
        "features": feat_reasons,
        "reliability": rel_reasons,
        "style": style_reasons,
    }
    items = [
        ScoreItem(key=key, name=name, max=mx, score=scores[key], reasons=reasons[key])
        for key, name, mx in _ITEM_META
    ]
    counted = [i for i in items if i.score is not None]
    raw_total = sum(i.score or 0.0 for i in counted)
    max_sum = sum(i.max for i in counted)
    total = percent_total(raw_total, max_sum)
    return ScoreResult(
        mode=mode,
        items=items,
        raw_total=raw_total,
        total=total,
        grade=grade_of(total),
        deductions=deductions,
    )
