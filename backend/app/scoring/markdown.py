"""把 Report 渲染成可下载的 Markdown。"""
from app.schemas import FEATURE_NAMES, KNOWLEDGE_NAMES, Report

_SOURCE = {"pipeline": "流水线", "agent": "智能体", "followup": "追问"}
_FEATURE_STATUS = {"done": "完成", "partial": "部分完成", "none": "未完成"}
_STYLE = {"good": "好", "medium": "中", "poor": "差"}


def _cell(text: object) -> str:
    return str(text).replace("\r", "").replace("\n", " ").replace("|", "\\|")


def _num(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _score_text(score: float | None, maximum: float) -> str:
    if score is None:
        return "不计分"
    return f"{_num(score)}/{_num(maximum)}"


def _fence(code: str) -> str:
    body = code if code else "（无）"
    fence = "````" if "```" in body else "```"
    return f"{fence}c\n{body}\n{fence}"


def render_markdown(report: Report) -> str:
    """导出报告 Markdown：标题、分数、功能点、缺陷、规范创新、工具调用和提示。"""
    project = report.project
    score = report.score
    lines: list[str] = [
        f"# 评测报告：{project.name}",
        "",
        f"- 任务号：{report.task_id}",
        f"- 生成时间：{report.generated_at}",
        f"- 总分：{score.total}（{score.grade}）",
        f"- 原始分：{score.raw_total}",
        "",
        report.summary,
        "",
        "## 分项分数",
        "",
        "| 项 | 得分/满分 | 原因 |",
        "| --- | --- | --- |",
    ]
    for item in score.items:
        lines.append(f"| {_cell(item.name)} | {_score_text(item.score, item.max)} | {_cell('；'.join(item.reasons))} |")

    lines += ["", "## 功能点", "", "| 编号 | 功能点 | 状态 | 理由 | 位置 |", "| --- | --- | --- | --- | --- |"]
    for feature in report.features:
        loc = "、".join(f"{c.path}:{c.line}" for c in feature.locations) or "—"
        lines.append(
            f"| {feature.feature_id} | {_cell(FEATURE_NAMES[feature.feature_id])} | "
            f"{_FEATURE_STATUS[feature.status]} | {_cell(feature.reason)} | {_cell(loc)} |"
        )

    lines += ["", "## 缺陷清单", ""]
    if not report.defects:
        lines.append("未发现缺陷。")
    for defect in report.defects:
        counted = "计分" if defect.counted else "不计分"
        if defect.in_baseline_unchanged:
            counted = "不计分（参考代码原有，不扣分）"
        elif defect.in_student_change:
            counted = f"{counted}（学生改动）"
        lines += [
            f"### [{defect.severity}] {defect.type_name} {defect.path}:{defect.line}",
            "",
            f"- 标题：{defect.title}",
            f"- 来源：{defect.source}",
            f"- 是否计分：{counted}",
            f"- 知识点：{KNOWLEDGE_NAMES[defect.knowledge_category]}",
            "",
            defect.description,
            "",
            defect.knowledge,
            "",
            f"建议：{defect.suggestion}",
            "",
            "改前：",
            "",
            _fence(defect.before),
            "",
            "改后：",
            "",
            _fence(defect.after),
            "",
        ]

    style = report.style
    innovation = report.innovation
    found = "代码中能找到" if innovation.found_in_code else "代码中未找到对应实现"
    lines += [
        "## 规范与创新",
        "",
        f"- 规范：{_STYLE[style.grade]}。{style.reason}",
        f"- 学生声称：{innovation.claimed or '（无）'}",
        f"- 创新评价：{found}。{innovation.comment}",
        "",
        "## 工具调用过程",
        "",
        "| seq | 来源 | 工具 | 状态 | 摘要 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for call in report.tool_calls:
        lines.append(
            f"| {call.seq} | {_SOURCE.get(call.source, call.source)} | {_cell(call.tool)} | "
            f"{_cell(call.status)} | {_cell(call.summary)} |"
        )

    lines += ["", "## warnings", ""]
    if report.warnings:
        lines.extend(f"- {item}" for item in report.warnings)
    else:
        lines.append("无")
    lines.append("")
    return "\n".join(lines)
