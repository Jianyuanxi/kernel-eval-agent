"""交叉编译 MiniEuler 工程并整理编译证据。"""
import re
import time
from pathlib import Path, PurePosixPath

from app import config
from app.schemas import BuildResult, Diagnostic, Project

from . import sandbox

_POSITION = re.compile(
    r"^(/workspace/[^:]+):(\d+):(\d+):\s+(warning|error|fatal error):\s*(.*)$"
)
_LINKER = re.compile(r"(?:^|/)(?:[\w-]*-)?ld(?:\.\w+)?:\s+(warning|error|fatal error):\s*(.*)$")


def parse_diagnostics(output: str) -> tuple[list[Diagnostic], int, int]:
    """按日志顺序编号诊断，完整计数并最多保留一百条证据。"""
    diagnostics: list[Diagnostic] = []
    warnings = errors = 0
    for line in output.splitlines():
        match = _POSITION.match(line)
        if match:
            raw_path, row, column, severity, message = match.groups()
            path = PurePosixPath(raw_path.removeprefix("/workspace/"))
            in_project = ".." not in path.parts and not path.is_absolute()
            relative = path.as_posix() if in_project else ""
            row_number, column_number = int(row), int(column)
        else:
            match = _LINKER.search(line)
            if not match:
                continue
            severity, message = match.groups()
            message = f"ld: {message}"
            relative, in_project, row_number, column_number = "", False, None, None
        severity = "warning" if severity == "warning" else "error"
        warnings += severity == "warning" and in_project
        errors += severity == "error"
        if len(diagnostics) < 100:
            diagnostics.append(Diagnostic(
                evidence_id=f"B{len(diagnostics) + 1}", severity=severity,
                path=relative, line=row_number, column=column_number,
                message=message, in_project=in_project,
            ))
    return diagnostics, warnings, errors


def find_artifact(work_dir: Path) -> str | None:
    """按课程工程命名顺序查找工作目录内的内核产物。"""
    root = work_dir.resolve()
    build_dir = root / "build"
    candidates = [build_dir / "miniEuler", build_dir / "miniEuler.elf"]
    candidates.extend(sorted(build_dir.rglob("*.elf")))
    for path in candidates:
        if path.is_file() and path.resolve().is_relative_to(root):
            return path.relative_to(root).as_posix()
    return None


def build(project: Project, project_dir: Path, work_dir: Path, log_dir: Path) -> BuildResult:
    """在工作副本中配置并编译，返回产物、诊断和有限日志。"""
    if not project.buildable:
        return BuildResult(status="unsupported")
    started = time.monotonic()
    rewritten = sandbox.prepare_workspace(project_dir, work_dir)
    source = "src" if (work_dir / "src/CMakeLists.txt").is_file() else "."
    result = sandbox.run_in_sandbox(
        ["sh", "-c", f"cmake -S {source} -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
         " && cmake --build build -j2"],
        work_dir, config.BUILD_TIMEOUT_S, name="ke-build",
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    output = result.output
    if result.truncated:
        output += f"\n[日志已截断，原始输出共 {result.output_bytes} 字节]\n"
    log_file = log_dir / "build.log"
    log_file.write_text(output, encoding="utf-8")
    diagnostics, warnings, errors = parse_diagnostics(result.output)
    if result.timed_out:
        if len(diagnostics) == 100:
            diagnostics.pop()
        diagnostics.append(Diagnostic(
            evidence_id=f"B{len(diagnostics) + 1}", severity="error", path="",
            message="编译超时", in_project=False,
        ))
        errors += 1
    artifact = find_artifact(work_dir)
    return BuildResult(
        status="passed" if result.exit_code == 0 and not result.timed_out and artifact else "failed",
        duration_s=round(time.monotonic() - started, 3), toolchain_rewritten=rewritten,
        warnings=warnings, errors=errors, diagnostics=diagnostics, artifact=artifact,
        has_compile_commands=(work_dir / "build/compile_commands.json").is_file(),
        log_tail=output[-3000:], log_file=str(log_file),
    )
