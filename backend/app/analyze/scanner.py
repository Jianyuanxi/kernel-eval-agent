"""逐文件执行 clang 静态分析并整理报告。"""
import json
import plistlib
import shlex
import time
from pathlib import Path, PurePosixPath

from app import config
from app.buildrun import sandbox
from app.schemas import DEFECT_TYPES, FileFailure, Finding, Project, ScanResult

FLAGS = [
    "-ffreestanding", "-fno-builtin",
    "-Wno-error=implicit-function-declaration", "-Wno-error=implicit-int",
    "-Wno-error=int-conversion", "-Wno-error=incompatible-pointer-types",
    "-Wno-error=incompatible-function-pointer-types",
]
SEPARATE = {"-I", "-D", "-include", "-isystem"}


def workspace_path(raw: str, directory: str = "/workspace") -> str | None:
    """把源文件路径规范到 /workspace 内，拒绝越界路径。"""
    path = PurePosixPath(raw.replace("\\", "/"))
    if not path.is_absolute():
        path = PurePosixPath(directory) / path
    parts = []
    for part in path.parts:
        if part in ("", "/", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    if not parts or parts[0] != "workspace":
        return None
    return "/" + "/".join(parts)


def extract_arguments(entry: dict) -> list[str]:
    """从编译数据库只取 clang 兼容的预处理和标准参数。"""
    tokens = entry.get("arguments")
    if tokens is None:
        tokens = shlex.split(entry.get("command", ""))
    directory = entry.get("directory", "/workspace")
    args = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in SEPARATE and i + 1 < len(tokens):
            value = tokens[i + 1]
            if token != "-D":
                value = workspace_path(value, directory) or value
            args.extend((token, value))
            i += 2
            continue
        if token.startswith("-std=") or token.startswith("-D") and token != "-D":
            args.append(token)
        elif token.startswith("-I") and token != "-I":
            args.append("-I" + (workspace_path(token[2:], directory) or token[2:]))
        elif token.startswith("-include") and token != "-include":
            value = token[len("-include"):]
            args.extend(("-include", workspace_path(value, directory) or value))
        elif token.startswith("-isystem") and token != "-isystem":
            value = token[len("-isystem"):].lstrip("=")
            args.extend(("-isystem", workspace_path(value, directory) or value))
        i += 1
    return args


def map_checker(checker: str, message: str) -> tuple[str | None, str | None]:
    """按评分规则第 8 节的表依次映射检查器。"""
    lower = message.lower()
    kind = None
    if checker in {"core.NullDereference", "core.NonNullParamChecker"} or checker.startswith("nullability."):
        kind = "NULL_DEREF"
    elif checker == "core.CallAndMessage" and "null" in lower:
        kind = "NULL_DEREF"
    elif checker == "core.CallAndMessage" and ("uninitialized" in lower or "garbage" in lower):
        kind = "UNINIT_VAR"
    elif checker == "core.DivideZero":
        kind = "DIV_ZERO"
    elif checker.startswith("core.uninitialized.") or checker == "core.UndefinedBinaryOperatorResult":
        kind = "UNINIT_VAR"
    elif checker in {"core.StackAddressEscape", "core.StackAddrEscapeBase"}:
        kind = "WILD_POINTER"
    elif checker in {"alpha.security.ArrayBoundV2", "security.ArrayBound", "alpha.unix.cstring.OutOfBounds"}:
        kind = "OUT_OF_BOUNDS"
    elif checker in {"unix.Malloc", "unix.MallocSizeof", "cplusplus.NewDelete"} and "use of memory after" in lower:
        kind = "USE_AFTER_FREE"
    elif checker == "unix.Malloc" and "attempt to free released" in lower:
        kind = "DOUBLE_FREE"
    elif checker == "unix.Malloc" and "leak" in lower:
        kind = "MEM_LEAK"
    elif checker.startswith("deadcode."):
        kind = "UNUSED"
    elif checker.startswith("security.insecureAPI."):
        kind = "OTHER_MINOR"
    elif checker.startswith("core."):
        kind = "OTHER_NORMAL"
    return kind, DEFECT_TYPES[kind][1] if kind else None


def parse_plist(data: bytes) -> list[Finding]:
    """提取 plist 中属于工程本身的诊断。"""
    document = plistlib.loads(data)
    files = document.get("files", [])
    findings = []
    for item in document.get("diagnostics", []):
        loc = item.get("location", {})
        file_index = loc.get("file")
        if not isinstance(file_index, int) or not 0 <= file_index < len(files):
            continue
        path = workspace_path(files[file_index])
        line = loc.get("line")
        if path is None or not isinstance(line, int) or line < 1:
            continue
        checker = str(item.get("check_name", ""))
        message = str(item.get("description", ""))
        kind, severity = map_checker(checker, message)
        findings.append(Finding(
            evidence_id="", checker=checker, path=path.removeprefix("/workspace/"),
            line=line, column=loc.get("col"), message=message,
            defect_type=kind, severity=severity,
        ))
    return findings


def finalize_findings(findings: list[Finding]) -> tuple[list[Finding], int]:
    """按路径、行号和检查器去重，按路径与行号排序编号。"""
    unique = {}
    for finding in findings:
        unique.setdefault((finding.path, finding.line, finding.checker), finding)
    ordered = sorted(unique.values(), key=lambda item: (item.path, item.line, item.checker))
    for index, finding in enumerate(ordered[:100], 1):
        finding.evidence_id = f"C{index}"
    return ordered[:100], len(ordered)


def _reason(output: str, fallback: str) -> str:
    """取第一条 clang 错误供文件失败记录使用。"""
    return next((line[line.find("error:"):].strip() for line in output.splitlines() if "error:" in line), fallback)


def _fragment_flags(work_dir: Path) -> list[str]:
    """收集工作副本中所有头文件目录。"""
    flags = ["-I", "/workspace"]
    for parent in sorted({p.parent for p in work_dir.rglob("*.h")}):
        relative = parent.relative_to(work_dir).as_posix()
        flags.extend(("-I", "/workspace" if relative == "." else f"/workspace/{relative}"))
    return flags


def run_scan(project: Project, project_dir: Path, work_dir: Path, log_dir: Path) -> ScanResult:
    """配置工程并扫描全部 C 文件，共享一个总时间预算。"""
    started = time.monotonic()
    sandbox.prepare_workspace(project_dir, work_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "scan.log"
    sources = sorted(p for p in work_dir.rglob("*.c") if p.is_file())
    target = {"aarch64": "aarch64-none-elf", "riscv64": "riscv64-unknown-elf"}.get(project.arch, "")
    if project.kind == "full":
        target = "aarch64-none-elf"
    deadline = started + config.SCAN_TIMEOUT_S
    entries: dict[str, list[str]] = {}
    logs = []
    if project.kind == "full":
        source_root = "src" if (work_dir / "src/CMakeLists.txt").is_file() else "."
        command = ["cmake", "-S", source_root, "-B", "build", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
        result = sandbox.run_in_sandbox(command, work_dir, max(1, int(deadline - time.monotonic())), name="ke-scan-config")
        logs.append(f"$ {shlex.join(command)}\nexit_code={result.exit_code} timed_out={result.timed_out}\n{result.output}\n")
        database = work_dir / "build/compile_commands.json"
        if result.exit_code == 0 and not result.timed_out and database.is_file():
            try:
                for entry in json.loads(database.read_text(encoding="utf-8", errors="replace")):
                    path = workspace_path(entry.get("file", ""), entry.get("directory", "/workspace"))
                    if path and path.endswith(".c"):
                        entries.setdefault(path, extract_arguments(entry))
            except (ValueError, TypeError) as exc:
                logs.append(f"compile_commands.json 无法解析：{exc}\n")
                entries.clear()
        else:
            logs.append("cmake 配置失败或没有编译数据库，改用片段参数。\n")
    fragment_flags = _fragment_flags(work_dir)
    (work_dir / "out").mkdir(exist_ok=True)
    failures = []
    findings = []
    scanned = 0
    for index, source in enumerate(sources, 1):
        relative = source.relative_to(work_dir).as_posix()
        if time.monotonic() >= deadline:
            failures.append(FileFailure(path=relative, reason="扫描总超时"))
            continue
        source_arg = f"/workspace/{relative}"
        command = ["clang", "--analyze"]
        if target:
            command.append(f"--target={target}")
        command.extend(FLAGS)
        command.extend(("-Xclang", "-analyzer-output=plist", "-o", f"/workspace/out/{index}.plist"))
        command.extend(entries.get(source_arg, fragment_flags))
        command.append(source_arg)
        result = sandbox.run_in_sandbox(command, work_dir, max(1, int(deadline - time.monotonic())), name="ke-scan")
        logs.append(f"$ {shlex.join(command)}\nexit_code={result.exit_code} timed_out={result.timed_out}\n{result.output}\n")
        plist_path = work_dir / "out" / f"{index}.plist"
        if plist_path.is_file():
            try:
                findings.extend(parse_plist(plist_path.read_bytes()))
                scanned += 1
            except (ValueError, TypeError, plistlib.InvalidFileException) as exc:
                failures.append(FileFailure(path=relative, reason=f"plist 无法解析：{exc}"))
        else:
            fallback = "clang 超时" if result.timed_out else "clang 未生成 plist"
            failures.append(FileFailure(path=relative, reason=_reason(result.output, fallback)))
    log_file.write_text("\n".join(logs), encoding="utf-8")
    ordered, total = finalize_findings(findings)
    return ScanResult(
        status="passed" if scanned else "unsupported", mode=project.kind, target=target,
        files_total=len(sources), files_scanned=scanned, files_failed=failures,
        coverage=round(scanned / len(sources), 2) if sources else 0,
        findings_total=total, findings=ordered, duration_s=round(time.monotonic() - started, 3),
        log_file=str(log_file),
    )
