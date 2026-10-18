"""块 5：智能体必须输出的 JSON（ReviewResult）。块 1 校验，块 6 据此算分。"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .common import CodeLocation, DefectType, FeatureId, KnowledgeCategory, Severity

FEATURE_IDS: list[str] = list(FeatureId.__args__)  # type: ignore[attr-defined]


class FeatureJudgement(BaseModel):
    feature_id: FeatureId
    status: Literal["done", "partial", "none"]
    reason: str = Field(description="一两句话说明依据")
    locations: list[CodeLocation] = []
    evidence_ids: list[str] = []


class ReviewDefect(BaseModel):
    type: DefectType
    path: str
    line: int = Field(ge=1)
    title: str = Field(description="一句话标题，如“申请的栈内存在出错分支未释放”")
    description: str = Field(description="问题描述：哪里、为什么错、会造成什么后果")
    source: Literal["clang", "gcc", "llm", "clang+llm", "gcc+llm"] = Field(
        description="clang=clang 告警原样采用；gcc=编译警告原样采用；llm=大模型读代码发现；x+llm=工具指出且大模型读代码确认")
    evidence_ids: list[str] = Field([], description="引用的证据编号，如 C3、S2")
    knowledge: str = Field(description="结合操作系统知识点的讲解，2–4 句")
    suggestion: str = Field(description="修改建议")
    before: str = Field("", description="改前代码（几行即可）")
    after: str = Field("", description="改后代码")


class StyleJudgement(BaseModel):
    grade: Literal["good", "medium", "poor"]
    reason: str


class InnovationJudgement(BaseModel):
    claimed: str = Field("", description="学生声称的创新（来自 README/说明文档/注释），没有则空串")
    found_in_code: bool
    comment: str
    locations: list[CodeLocation] = []


class ReviewResult(BaseModel):
    summary: str = Field(description="总体评语，100–200 字")
    features: list[FeatureJudgement]
    defects: list[ReviewDefect] = Field([], max_length=30)
    style: StyleJudgement
    innovation: InnovationJudgement

    @field_validator("features")
    @classmethod
    def _eight_features(cls, v: list[FeatureJudgement]) -> list[FeatureJudgement]:
        ids = [f.feature_id for f in v]
        if sorted(ids) != sorted(FEATURE_IDS):
            raise ValueError(f"features 必须恰好包含 8 个功能点各一次：{FEATURE_IDS}，实际 {ids}")
        return v


class ReportDefect(ReviewDefect):
    """块 1 校验并补全后写进报告的缺陷"""
    severity: Severity
    type_name: str
    knowledge_category: KnowledgeCategory
    in_student_change: bool | None = Field(None, description="落在学生改动/新增的行里；没有参考基线时为 null")
    in_baseline_unchanged: bool = Field(False, description="所在文件与参考代码完全相同：只展示，不扣分")
    counted: bool = Field(False, description="是否计入可靠性扣分（由块 6 评分时填写）")
