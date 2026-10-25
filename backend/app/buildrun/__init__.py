"""块 3：编译与运行。build/run 签名已冻结；公共沙箱执行器在 sandbox.py（块 4 也用）。

实现要求见 docs/tasks/块3-编译与运行.md。
"""
from pathlib import Path

from app.schemas import BuildResult, Project, RunResult
from .compiler import build as _build


def build(project: Project, project_dir: Path, work_dir: Path, log_dir: Path) -> BuildResult:
    """把 project_dir 拷到 work_dir（prepare_workspace），在沙箱里 cmake 配置 + 构建。

    work_dir 挂载为容器内 /workspace；产物和 compile_commands.json 留在 work_dir/build/ 供 run 使用。
    完整日志写 log_dir/build.log。project.buildable 为 false 时返回 status="unsupported"。
    """
    return _build(project, project_dir, work_dir, log_dir)


def run(project: Project, work_dir: Path, build_result: BuildResult, log_dir: Path) -> RunResult:
    """在 QEMU 中运行 build_result.artifact，固定窗口 KE_RUN_WINDOW_S 秒，识别到 shell 时发命令。

    build_result.status != "passed" 时直接返回 status="skipped"。完整串口输出写 log_dir/run.log。
    """
    raise NotImplementedError
