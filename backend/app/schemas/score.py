"""块 6：评分结果"""
from typing import Literal

from pydantic import BaseModel, Field

from .common import Severity


class ScoreItem(BaseModel):
    key: Literal["compile_run", "features", "reliability", "style"]
    name: str
    max: float
    score: float | None = Field(description="片段模式下 compile_run 为 null（不计）")
    reasons: list[str] = []


class Deduction(BaseModel):
    defect_index: int = Field(description="Report.defects 里的下标")
    type: str
    severity: Severity
    points: int


class ScoreResult(BaseModel):
    mode: Literal["full", "fragment"]
    items: list[ScoreItem]
    raw_total: float = Field(description="四项相加（片段模式为三项之和折算前）")
    total: int = Field(description="百分制，四舍五入")
    grade: Literal["优秀", "良好", "中等", "及格", "不及格"]
    deductions: list[Deduction] = []
