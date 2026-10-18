"""公共契约。所有块之间只通过这里的模型交换数据。

修改规则（docs/02-接口规范.md 第 1 节）：
- 只加可选字段（有默认值）算兼容修改，在群里说一声即可；
- 改名、删字段、改类型、改枚举值都是破坏性修改，必须组长同意，并同步改 contracts/examples。
"""
from .analyze import FileFailure, Finding, ScanResult
from .buildrun import BuildResult, Diagnostic, ExecResult, RunCommand, RunResult
from .common import (
    DEFECT_TYPES, FEATURE_NAMES, KNOWLEDGE_NAMES, SEVERITY_PENALTY,
    CodeLocation, DefectType, ErrorInfo, FeatureId, LineRange, Severity, Status,
)
from .ingest import DiffResult, FileChange, FileEntry, FileList, IngestResult, Project, SourceSlice
from .review import (
    FEATURE_IDS, FeatureJudgement, InnovationJudgement, ReportDefect, ReviewDefect, ReviewResult, StyleJudgement,
)
from .score import Deduction, ScoreItem, ScoreResult
from .task import (
    AgentThought, EventsResponse, FollowupRequest, FollowupResponse, Report, StartRequest, TaskInfo, ToolCallRecord,
)
from .tools import ProjectRef, ReadSourceRequest
