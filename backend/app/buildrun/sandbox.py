"""公共沙箱执行器（块 3 维护，块 4 也调用）。

当前是 2026-10-18 在服务器上用样例 1、2、4 验证过的最小实现；块 3 负责加固（输出上限、清理、异常处理、测试），
但不改函数签名。
"""
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

from app.config import SANDBOX_IMAGE
from app.schemas import ExecResult

TOOLCHAIN = "/opt/toolchain"  # 沙箱镜像里的统一工具链路径，见 sandbox/Dockerfile


class SandboxError(RuntimeError):
    """docker 不可用、镜像不存在等工具自身问题。调用方转成 status="error" + SANDBOX_ERROR"""


def run_in_sandbox(cmd: list[str], work_dir: Path, timeout_s: int, *, name: str,
                   stdin_steps: list[tuple[float, str]] | None = None,
                   max_output: int = 256 * 1024) -> ExecResult:
    """在一次性容器里执行 cmd。work_dir 挂载为 /workspace，断网、非 root、限 CPU/内存/进程数。

    stdin_steps：[(等待秒数, 要写入的文本), ...]，按顺序写进容器 stdin（给 QEMU 串口发 shell 命令用）。
    超时后按容器名强制删除容器，返回 timed_out=True、exit_code=None。
    """
    if shutil.which("docker") is None:
        raise SandboxError("找不到 docker 命令：编译/运行/扫描只能在装了 Docker 的 Linux（服务器或 WSL2）上跑")
    cname = f"{name}-{secrets.token_hex(3)}"
    user = [] if not hasattr(os, "getuid") else ["--user", f"{os.getuid()}:{os.getgid()}"]
    docker_cmd = [
        "docker", "run", "--rm", "-i", "--name", cname,
        "--network", "none", *user, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--cpus", "2", "--memory", "1g", "--pids-limit", "256",
        "-v", f"{Path(work_dir).resolve()}:/workspace", "-w", "/workspace",
        SANDBOX_IMAGE, *cmd,
    ]
    start = time.monotonic()
    proc = subprocess.Popen(docker_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = bytearray()
    total = 0

    def _read() -> None:
        nonlocal total
        assert proc.stdout is not None
        for chunk in iter(lambda: proc.stdout.read(4096), b""):
            total += len(chunk)
            if len(buf) < max_output:
                buf.extend(chunk[: max_output - len(buf)])

    def _write() -> None:
        assert proc.stdin is not None
        try:
            for delay, text in stdin_steps or []:
                time.sleep(delay)
                proc.stdin.write(text.encode())
                proc.stdin.flush()
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    reader = threading.Thread(target=_read, daemon=True)
    writer = threading.Thread(target=_write, daemon=True)
    reader.start()
    writer.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            subprocess.run(["docker", "rm", "-f", cname], capture_output=True, timeout=5)
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired as e:
            raise SandboxError(f"超时后清理容器 {cname} 失败（docker 无响应），需要人工 docker rm -f") from e
        finally:
            if proc.poll() is None:
                proc.kill()  # 本地 docker 客户端进程
    reader.join(timeout=5)
    out = buf.decode("utf-8", errors="replace").replace("\x00", "")
    if not timed_out and proc.returncode == 125:
        raise SandboxError(f"docker run 失败：{out[:500]}")
    return ExecResult(
        exit_code=None if timed_out else proc.returncode,
        timed_out=timed_out,
        output=out,
        output_bytes=total,
        truncated=total > max_output,
        duration_s=round(time.monotonic() - start, 2),
    )


_TC_SET = re.compile(r'set\(\s*TOOLCHAIN_PATH\s+"?[^\s)"]+"?\s*\)')
_TC_ABS = re.compile(r'/[^\s"()]*?/bin/aarch64-none-elf-')


def prepare_workspace(project_dir: Path, work_dir: Path) -> list[str]:
    """把工程拷到 work_dir，并把各 CMakeLists.txt 里写死的工具链路径改写成沙箱里的 /opt/toolchain。

    原始工程目录不动。返回被改写的文件（相对工程根）。已验证的写法：
    set(TOOLCHAIN_PATH /root/aarch64-none-elf)、set(CMAKE_C_COMPILER /opt/buildtools/gcc-arm-10.3-.../bin/aarch64-none-elf-gcc)
    """
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(project_dir, work_dir)
    changed = []
    for p in sorted(work_dir.rglob("CMakeLists.txt")):
        text = p.read_text(encoding="utf-8", errors="replace")
        new = _TC_SET.sub(f"set(TOOLCHAIN_PATH {TOOLCHAIN})", text)
        new = _TC_ABS.sub(f"{TOOLCHAIN}/bin/aarch64-none-elf-", new)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(p.relative_to(work_dir).as_posix())
    return changed
