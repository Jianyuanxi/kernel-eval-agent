"""全项目共用的枚举、错误码和小模型。改这里等于改接口，必须先在群里说并由块 1 合并。"""
from typing import Literal

from pydantic import BaseModel, Field

# 工具/步骤的执行结果状态。工具自身出错用 error，不能和“学生代码编译失败”(failed) 混用
Status = Literal["passed", "failed", "timeout", "skipped", "unsupported", "error"]

# 错误码：前端按 code 显示提示，message 是给人看的中文
ErrorCode = Literal[
    "UPLOAD_TOO_LARGE",      # 上传或解压后超过大小/文件数上限
    "UPLOAD_BAD_TYPE",       # 不是 zip，也不是 .c/.h
    "UPLOAD_BAD_ZIP",        # zip 损坏或加密
    "UPLOAD_UNSAFE_PATH",    # zip 里有绝对路径、.. 或符号链接
    "NO_SOURCE_FOUND",       # 解压后找不到任何 .c 文件
    "TASK_NOT_FOUND",
    "PROJECT_NOT_FOUND",
    "TASK_STATE_CONFLICT",   # 例如任务已在运行又调用 start
    "REQUEST_INVALID",       # 请求参数不合法（缺字段、类型不对、行号 < 1 等）
    "PATH_INVALID",          # read_source 等传入了工程外或不存在的路径
    "TOOL_TOKEN_INVALID",
    "RESULT_NOT_READY",      # 工具被调用时对应结果还没生成
    "SANDBOX_ERROR",         # docker 起不来、镜像不存在等
    "AGENT_ERROR",           # Dify 返回错误
    "AGENT_TIMEOUT",
    "AGENT_SKIPPED_TOOLS",   # 提醒一次后智能体仍未调用必需工具
    "REVIEW_INVALID",        # 修复一次后智能体输出仍不符合 ReviewResult
    "INTERNAL_ERROR",
]


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str


class LineRange(BaseModel):
    """闭区间，行号从 1 开始"""
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class CodeLocation(BaseModel):
    path: str = Field(description="相对工程根目录，分隔符统一用 /")
    line: int = Field(ge=1)


# ---------- 功能点与缺陷类型（评分规则依赖它们，见 docs/03-评分规则.md） ----------

FeatureId = Literal["F_UART", "F_EXC", "F_TIMER", "F_TASK", "F_SCHED", "F_SEM", "F_SHELL", "F_INNOV"]

FEATURE_NAMES: dict[str, str] = {
    "F_UART": "串口打印",
    "F_EXC": "异常处理",
    "F_TIMER": "时钟中断",
    "F_TASK": "任务创建与切换",
    "F_SCHED": "任务调度",
    "F_SEM": "信号量",
    "F_SHELL": "shell 命令",
    "F_INNOV": "创新功能",
}

Severity = Literal["严重", "一般", "轻微"]

DefectType = Literal[
    # 严重
    "NULL_DEREF", "OUT_OF_BOUNDS", "USE_AFTER_FREE", "DOUBLE_FREE", "WILD_POINTER", "DIV_ZERO",
    "DEADLOCK", "LOCK_NOT_RELEASED", "RACE", "IRQ_NOT_RESTORED", "CONTEXT_SAVE", "OTHER_SEVERE",
    # 一般
    "MEM_LEAK", "UNINIT_VAR", "UNCHECKED_RETURN", "UNCHECKED_PARAM", "RESOURCE_NOT_CLOSED",
    "LOCK_ORDER", "IRQ_LONG_WAIT", "OTHER_NORMAL",
    # 轻微
    "UNUSED", "MAGIC_NUMBER", "NO_COMMENT", "OTHER_MINOR",
]

KnowledgeCategory = Literal["K_MEM", "K_ADDR", "K_SYNC", "K_CRIT", "K_IRQ", "K_CTX", "K_SYSCALL", "K_DEV", "K_GENERAL"]

KNOWLEDGE_NAMES: dict[str, str] = {
    "K_MEM": "内存管理（内存的分配与回收）",
    "K_ADDR": "地址空间与内存保护",
    "K_SYNC": "进程同步与互斥、死锁的四个必要条件",
    "K_CRIT": "临界区、竞态条件",
    "K_IRQ": "中断机制",
    "K_CTX": "进程控制块与上下文切换",
    "K_SYSCALL": "系统调用、用户态与内核态隔离",
    "K_DEV": "文件系统与设备管理",
    "K_GENERAL": "通用编程规范与健壮性",
}

# 缺陷类型 -> (中文名, 级别, 知识点)。级别由类型决定，大模型不能自己改级别
DEFECT_TYPES: dict[str, tuple[str, str, str]] = {
    "NULL_DEREF": ("空指针解引用", "严重", "K_ADDR"),
    "OUT_OF_BOUNDS": ("数组越界", "严重", "K_ADDR"),
    "USE_AFTER_FREE": ("释放后使用", "严重", "K_MEM"),
    "DOUBLE_FREE": ("重复释放", "严重", "K_MEM"),
    "WILD_POINTER": ("野指针", "严重", "K_ADDR"),
    "DIV_ZERO": ("除零", "严重", "K_GENERAL"),
    "DEADLOCK": ("死锁", "严重", "K_SYNC"),
    "LOCK_NOT_RELEASED": ("加锁后未释放", "严重", "K_SYNC"),
    "RACE": ("共享变量未加保护", "严重", "K_CRIT"),
    "IRQ_NOT_RESTORED": ("关中断后未恢复", "严重", "K_IRQ"),
    "CONTEXT_SAVE": ("上下文保存不完整", "严重", "K_CTX"),
    "OTHER_SEVERE": ("其他严重问题", "严重", "K_GENERAL"),
    "MEM_LEAK": ("内存泄漏", "一般", "K_MEM"),
    "UNINIT_VAR": ("使用未初始化的变量", "一般", "K_GENERAL"),
    "UNCHECKED_RETURN": ("返回值未检查", "一般", "K_GENERAL"),
    "UNCHECKED_PARAM": ("参数或用户指针未检查", "一般", "K_SYSCALL"),
    "RESOURCE_NOT_CLOSED": ("资源未释放或出错分支未清理", "一般", "K_DEV"),
    "LOCK_ORDER": ("加锁顺序不一致", "一般", "K_SYNC"),
    "IRQ_LONG_WAIT": ("中断处理中长时间等待", "一般", "K_IRQ"),
    "OTHER_NORMAL": ("其他一般问题", "一般", "K_GENERAL"),
    "UNUSED": ("变量或函数未使用", "轻微", "K_GENERAL"),
    "MAGIC_NUMBER": ("魔法数字", "轻微", "K_GENERAL"),
    "NO_COMMENT": ("缺少注释", "轻微", "K_GENERAL"),
    "OTHER_MINOR": ("其他轻微问题", "轻微", "K_GENERAL"),
}

SEVERITY_PENALTY: dict[str, int] = {"严重": 5, "一般": 2, "轻微": 1}
