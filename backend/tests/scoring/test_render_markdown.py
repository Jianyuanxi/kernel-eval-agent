"""块 6 阶段 2：报告 Markdown 导出。"""
import json

from app.config import EXAMPLES_DIR
from app.schemas import Report
from app.scoring import render_markdown


def _report() -> Report:
    data = json.loads((EXAMPLES_DIR / "report.json").read_text(encoding="utf-8"))
    return Report.model_validate(data)


def test_sample_report_markdown():
    """示例报告以标题开头，含总分、等级和每条缺陷的 path:line。"""
    report = _report()
    text = render_markdown(report)
    assert text.startswith("#")
    assert "79" in text
    assert "中等" in text
    for defect in report.defects:
        assert f"{defect.path}:{defect.line}" in text
    assert "编译与运行" in text
    assert "功能完成度" in text
    assert "规范与创新" in text
    assert "| seq | 来源 | 工具 | 状态 | 摘要 |" in text
    assert "warnings" in text


def test_null_score_item_shows_not_counted():
    report = _report()
    report.score.items[0].score = None
    text = render_markdown(report)
    assert "不计分" in text
    assert "19/20" not in text.split("## 功能点", 1)[0]
