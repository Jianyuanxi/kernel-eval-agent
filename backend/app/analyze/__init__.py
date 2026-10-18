"""块 4：clang 静态分析。scan 签名已冻结。

实现要求见 docs/tasks/块4-静态分析与缺陷测试.md。
"""
from pathlib import Path

from app.schemas import Project, ScanResult


def scan(project: Project, project_dir: Path, work_dir: Path, log_dir: Path) -> ScanResult:
    """对工程里的 .c 文件逐个跑 clang --analyze。

    kind=full：用 buildrun.sandbox.prepare_workspace 拷到 work_dir，只做 cmake 配置拿 compile_commands.json
    （不要求编译成功），按每个文件的 -I/-D/-include/-std 参数扫描。
    kind=fragment：每个 .c 单独扫，-I 指向片段目录；缺头文件扫不了的记进 files_failed，不能当作零缺陷。
    完整日志写 log_dir/scan.log。
    """
    raise NotImplementedError
