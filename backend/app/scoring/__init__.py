"""块 6：评分（纯函数，不调大模型、不读文件）和报告导出。签名已冻结。

评分规则见 docs/03-评分规则.md，实现要求见 docs/tasks/块6-网页评分与追问.md。
"""
from app.schemas import BuildResult, Project, Report, ReportDefect, ReviewResult, RunResult, ScoreResult
from app.scoring.compute import compute_score as _compute_score
from app.scoring.markdown import render_markdown as _render_markdown


def compute_score(project: Project, build: BuildResult | None, run: RunResult | None,
                  review: ReviewResult, defects: list[ReportDefect]) -> ScoreResult:
    """按 docs/03 计算分数。会就地设置 defects[i].counted（是否计入可靠性扣分）。

    同样的输入必须得到同样的输出。
    """
    return _compute_score(project, build, run, review, defects)


def render_markdown(report: Report) -> str:
    """把报告导出成 Markdown（GET /api/tasks/{id}/export?format=md 用）"""
    return _render_markdown(report)
