"""启动 QEMU 并把串口输出整理为可引用的运行证据。"""
import math
import re
import time
from collections import Counter
from pathlib import Path

from app import config
from app.schemas import BuildResult, Project, RunCommand, RunResult

from . import sandbox

_GIC = re.compile(r"gic-version=(\d)|\bGIC_VERSION\s+(\d)")
_NAMED_COMMAND = re.compile(r'(?:strcmp|strncmp)\s*\(\s*\w+\s*,\s*"(\w+)"|\{\s*"(\w+)"\s*,')
_CHAR_COMMAND = re.compile(
    r"\b(\w+)\s*\[\s*0\s*\]\s*==\s*'\w'"
    r"(?:\s*&&\s*\1\s*\[\s*\d+\s*\]\s*==\s*'\w')+"
)
_PROMPT = re.compile(r"^(\S[^\n]{0,30}?[#$>] )", re.MULTILINE)
_MAX_OUTPUT = 256 * 1024


def _read_source(path: Path, work_dir: Path) -> str:
    """构建后也不跟随指向工作区外的链接读取宿主文件。"""
    if path.is_file() and path.resolve().is_relative_to(work_dir.resolve()):
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def detect_gic(work_dir: Path) -> int:
    """优先读取启动脚本，缺失时从课程源文件和注释判断 GIC。"""
    script = work_dir / "runMiniEuler.sh"
    if script.is_file():
        matches = list(re.finditer(r"gic-version=(\d)", _read_source(script, work_dir)))
        if matches:
            return int(matches[-1][1])
    for path in sorted((work_dir / "src").rglob("*")):
        if path.is_file() and path.suffix.lower() in {".c", ".h", ".s"}:
            match = _GIC.search(_read_source(path, work_dir))
            if match:
                return int(match[1] or match[2])
    return 2


def extract_commands(work_dir: Path) -> list[str]:
    """提取 shell 命令，兼容字符串比较、命令表及逐字符判断。"""
    commands = ["top", "tick"]
    paths = sorted(p for p in (work_dir / "src").rglob("*.c") if "shell" in p.parent.parts)
    for path in paths:
        text = _read_source(path, work_dir)
        found = [(m.start(), m[1] or m[2]) for m in _NAMED_COMMAND.finditer(text)]
        for match in _CHAR_COMMAND.finditer(text):
            chars = re.findall(r"\[\s*(\d+)\s*\]\s*==\s*'(\w)'", match[0])
            if [int(index) for index, _ in chars] == list(range(len(chars))):
                found.append((match.start(), "".join(char for _, char in chars)))
        for _, command in sorted(found):
            if command not in commands:
                commands.append(command)
            if len(commands) == 6:
                return commands
    return commands


def normalize_output(output: str) -> str:
    """统一串口换行、合并空行并去掉空字符。"""
    return re.sub(r"\n+", "\n", output.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n"))


def serial_output(output: str) -> str:
    """排除 QEMU 自身的状态行，保留内核打印内容。"""
    return "\n".join(line for line in normalize_output(output).split("\n")
                     if not line.lstrip().startswith("qemu-system-aarch64:"))


def split_output(output: str, sent_commands: list[str]) -> tuple[str, str | None, list[RunCommand]]:
    """用带命令回显的真实提示符切分启动与命令输出。"""
    text = serial_output(output)
    first = next((m for m in _PROMPT.finditer(text)
                  if text[m.end():].split("\n", 1)[0].strip() in sent_commands), None)
    if first is None:
        return text[:4000], None, []
    prompt = first[1]
    sections = re.split(r"^" + re.escape(prompt), text[first.start():], flags=re.MULTILINE)
    commands: list[RunCommand] = []
    for section in sections[1:]:
        echo, _, response = section.partition("\n")
        if echo.strip() in sent_commands:
            commands.append(RunCommand(
                evidence_id=f"R{len(commands) + 2}", command=echo.strip(),
                output=response.strip("\n")[:4000],
            ))
    return text[:first.start()][:4000], prompt, commands


def feature_hints(booted: bool, commands: list[RunCommand]) -> list[str]:
    """只从已观察到的串口证据给出功能提示。"""
    hints = ["F_UART"] if booted else []
    if any(c.command == "tick" and re.search(r"\d", c.output) for c in commands):
        hints.append("F_TIMER")
    if any(c.command == "top" and re.search(r"^\s*\d+\s+\d+\s+\d+", c.output, re.MULTILINE)
           for c in commands):
        hints.append("F_TASK")
    if any(c.output.strip() for c in commands):
        hints.append("F_SHELL")
    return hints


def run(project: Project, work_dir: Path, build_result: BuildResult, log_dir: Path) -> RunResult:
    """在有限时间内运行内核，必要时切换 GIC，并记录命令与异常。"""
    if build_result.status != "passed":
        return RunResult(status="skipped", window_s=config.RUN_WINDOW_S)
    started = time.monotonic()
    artifact = build_result.artifact
    if not artifact or not (work_dir / artifact).is_file() or Path(artifact).is_absolute() \
            or not (work_dir / artifact).resolve().is_relative_to(work_dir.resolve()):
        raise sandbox.SandboxError("编译结果中的内核产物不存在或越出工作目录")
    window = config.RUN_WINDOW_S
    deadline = started + 2 * window + 20
    gic = detect_gic(work_dir)
    sent = extract_commands(work_dir)
    steps = [(5 if index == 0 else 2, command + "\r") for index, command in enumerate(sent)]
    attempts = []
    for _ in range(2):
        timeout_s = min(window + 10, max(1, math.floor(deadline - time.monotonic() - 5)))
        result = sandbox.run_in_sandbox(
            ["timeout", str(window), "qemu-system-aarch64", "-machine", f"virt,gic-version={gic}",
             "-m", "1024M", "-cpu", "cortex-a53", "-nographic", "-nic", "none",
             "-serial", "mon:stdio", "-kernel", artifact],
            work_dir, timeout_s, name="ke-run", stdin_steps=steps,
        )
        attempts.append((gic, result))
        if serial_output(result.output).strip():
            break
        gic = 3 if gic == 2 else 2
    guest = serial_output(attempts[-1][1].output)
    booted = bool(guest.strip())
    counts = Counter(line.strip() for line in guest.splitlines() if line.strip())
    anomalies = []
    if any(count >= 50 for count in counts.values()):
        anomalies.append("EXC_STORM")
    if len(attempts) == 1:
        raw = attempts[0][1].output
    else:
        raw = "\n".join(f"===== gic-version={version} =====\n{r.output}" for version, r in attempts)
    encoded = raw.encode("utf-8")
    if any(r.truncated for _, r in attempts) or len(encoded) > _MAX_OUTPUT:
        anomalies.append("OUTPUT_TRUNCATED")
    if not booted:
        anomalies.append("NO_OUTPUT")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "run.log"
    log_file.write_bytes(encoded[:_MAX_OUTPUT])
    boot_output, prompt, commands = split_output(attempts[-1][1].output, sent)
    return RunResult(
        status="passed" if booted and "EXC_STORM" not in anomalies else "failed",
        booted=booted, gic_version=attempts[-1][0], tried_gic=[version for version, _ in attempts],
        window_s=window, boot_output=boot_output, shell_prompt=prompt, commands=commands,
        feature_hints=feature_hints(booted, commands), anomalies=anomalies,
        output_bytes=sum(r.output_bytes for _, r in attempts),
        duration_s=round(time.monotonic() - started, 3), log_file=str(log_file),
    )
