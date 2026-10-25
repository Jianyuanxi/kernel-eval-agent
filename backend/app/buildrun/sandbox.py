"""公共沙箱执行器（块 3 维护，块 4 也调用）。

执行器使用有限输出缓冲、可取消输入线程和限时清理，公共函数签名保持不变。
"""
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import json
from datetime import datetime, timezone
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
    if timeout_s <= 0 or max_output < 0 or not cmd:
        raise ValueError("沙箱命令、超时或输出上限无效")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,60}", name):
        raise ValueError("沙箱容器名前缀无效")
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    gid = os.getgid() if hasattr(os, "getgid") else 1000
    if uid == 0:
        raise SandboxError("请使用普通用户执行沙箱测试，不能以 root 身份运行学生工程")
    cname = f"{name}-{secrets.token_hex(3)}"
    docker_cmd = [
        "docker", "run", "--rm", "-i", "--name", cname,
        "--label", "kernel-eval=1", "--label", f"kernel-eval.owner={uid}",
        "--network", "none", "--user", f"{uid}:{gid}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--cpus", "2", "--memory", "1g", "--pids-limit", "256",
        "-v", f"{Path(work_dir).resolve()}:/workspace", "-w", "/workspace",
        SANDBOX_IMAGE, *cmd,
    ]
    start = time.monotonic()
    try:
        proc = subprocess.Popen(docker_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        raise SandboxError(f"无法启动 docker：{exc}") from exc
    buf = bytearray()
    total = 0
    stop = threading.Event()

    def _read() -> None:
        nonlocal total
        assert proc.stdout is not None
        try:
            for chunk in iter(lambda: os.read(proc.stdout.fileno(), 65536), b""):
                total += len(chunk)
                if len(buf) < max_output:
                    buf.extend(chunk[: max_output - len(buf)])
        except (OSError, ValueError):
            pass

    def _write() -> None:
        assert proc.stdin is not None
        try:
            for delay, text in stdin_steps or []:
                if stop.wait(delay):
                    break
                proc.stdin.write(text.encode("utf-8"))
                proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass

    reader = threading.Thread(target=_read, daemon=True)
    writer = threading.Thread(target=_write, daemon=True)
    reader.start()
    writer.start()
    timed_out = False
    cleanup_error = None
    try:
        proc.wait(timeout=max(0.01, timeout_s - (time.monotonic() - start)))
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        stop.set()
        try:
            removed = subprocess.run(["docker", "rm", "-f", cname], capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", timeout=2)
            if removed.returncode and "no such container" not in removed.stderr.lower():
                cleanup_error = removed.stderr[:300]
        except (subprocess.TimeoutExpired, OSError) as exc:
            cleanup_error = str(exc)
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            cleanup_error = cleanup_error or "docker 客户端无法结束"
        reader.join(timeout=0.5)
        writer.join(timeout=0.5)
        if proc.stdout is not None:
            proc.stdout.close()
    out = buf.decode("utf-8", errors="replace")
    if not timed_out and proc.returncode in {125, 126, 127}:
        raise SandboxError(f"docker run 失败：{out[:500]}")
    if cleanup_error or reader.is_alive() or writer.is_alive():
        raise SandboxError(f"清理容器 {cname} 失败：{cleanup_error or '日志或输入线程未结束'}")
    return ExecResult(
        exit_code=None if timed_out else proc.returncode,
        timed_out=timed_out,
        output=out,
        output_bytes=total,
        truncated=total > max_output,
        duration_s=round(time.monotonic() - start, 2),
    )


def cleanup_stale() -> list[str]:
    """仅清理当前用户创建、带项目标签且运行超过十分钟的容器。"""
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    try:
        listing = subprocess.run(
            ["docker", "ps", "-q", "--filter", "label=kernel-eval=1",
             "--filter", f"label=kernel-eval.owner={uid}"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        ids = listing.stdout.split()
        if not ids:
            return []
        if not all(re.fullmatch(r"[0-9a-f]{12,64}", item) for item in ids):
            raise SandboxError("docker 返回了无效容器编号")
        inspected = subprocess.run(["docker", "inspect", *ids], capture_output=True,
                                   text=True, timeout=5, check=True)
        removed = []
        now = datetime.now(timezone.utc)
        for container in json.loads(inspected.stdout):
            labels = container.get("Config", {}).get("Labels") or {}
            state = container.get("State", {})
            if labels.get("kernel-eval") != "1" or labels.get("kernel-eval.owner") != str(uid) \
                    or not state.get("Running") or container.get("Id", "")[:12] not in {i[:12] for i in ids}:
                continue
            started = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
            if (now - started).total_seconds() > 600:
                subprocess.run(["docker", "rm", "-f", container["Id"]], capture_output=True,
                               timeout=2, check=True)
                removed.append(container["Id"])
        return removed
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise SandboxError(f"检查过期沙箱失败：{exc}") from exc


_TC_SET = re.compile(r'set\(\s*TOOLCHAIN_PATH\s+"?[^\s)"]+"?\s*\)')
_TC_ABS = re.compile(r'/[^\s"()]*?/bin/aarch64-none-elf-')


def prepare_workspace(project_dir: Path, work_dir: Path) -> list[str]:
    """把工程拷到 work_dir，并把各 CMakeLists.txt 里写死的工具链路径改写成沙箱里的 /opt/toolchain。

    原始工程目录不动。返回被改写的文件（相对工程根）。已验证的写法：
    set(TOOLCHAIN_PATH /root/aarch64-none-elf)、set(CMAKE_C_COMPILER /opt/buildtools/gcc-arm-10.3-.../bin/aarch64-none-elf-gcc)
    """
    source, destination = project_dir.resolve(), work_dir.resolve()
    if project_dir.is_symlink() or work_dir.is_symlink() or source == destination \
            or source in destination.parents or destination in source.parents:
        raise SandboxError("原始工程与工作目录不能重叠或使用符号链接")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise SandboxError("工程中存在符号链接，拒绝复制工作区外的文件")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(project_dir, work_dir)
    stale_build = work_dir / "build"
    if stale_build.is_dir():
        shutil.rmtree(stale_build)
    changed = []
    for p in sorted(work_dir.rglob("CMakeLists.txt")):
        text = p.read_text(encoding="utf-8", errors="replace")
        new = _TC_SET.sub(f"set(TOOLCHAIN_PATH {TOOLCHAIN})", text)
        new = _TC_ABS.sub(f"{TOOLCHAIN}/bin/aarch64-none-elf-", new)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(p.relative_to(work_dir).as_posix())
    return changed
