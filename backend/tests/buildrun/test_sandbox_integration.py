"""真实容器隔离、输出限制、故障内核和全部实验编译验收。"""
import secrets
import subprocess
import time
from pathlib import Path

import pytest

from app.buildrun import build, run, sandbox
from app import config
from .conftest import project_for

pytestmark = pytest.mark.sandbox


def tiny_kernel(directory: Path, source: str) -> None:
    """生成自写的最小裸机内核，故障测试不依赖往届样例实现。"""
    directory.mkdir()
    (directory / "CMakeLists.txt").write_text('''cmake_minimum_required(VERSION 3.12)
set(CMAKE_SYSTEM_NAME Generic)
set(TOOLCHAIN_PATH /old/toolchain)
set(CMAKE_C_COMPILER ${TOOLCHAIN_PATH}/bin/aarch64-none-elf-gcc)
set(CMAKE_ASM_COMPILER ${TOOLCHAIN_PATH}/bin/aarch64-none-elf-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(TestKernel LANGUAGES C ASM)
add_executable(miniEuler start.S main.c)
target_compile_options(miniEuler PRIVATE -ffreestanding -fno-builtin -fno-stack-protector -Os)
target_link_options(miniEuler PRIVATE -nostdlib -Wl,--build-id=none -Wl,-Ttext=0x40000000 -Wl,-e,_start)
''', encoding="utf-8")
    (directory / "start.S").write_text(
        ".global _start\n_start:\n ldr x0, =0x41000000\n mov sp, x0\n bl main\n b .\n", encoding="utf-8")
    (directory / "main.c").write_text(source, encoding="utf-8")


@pytest.mark.parametrize("lab", ["lab1", "lab2", "lab2_hw1", "lab4", "lab5", "lab5_pro",
                                 "lab6", "lab6_pro", "lab8", "lab9", "lab10"])
def test_every_lab_builds(sample_root: Path, tmp_path: Path, lab: str):
    """样例二的十一个独立实验全部实际编译。"""
    directory = sample_root / "样例2_分阶段工程" / lab
    if not directory.is_dir():
        pytest.skip(f"没有样例 2 {lab}")
    result = build(project_for(directory), directory, tmp_path / "work", tmp_path / "logs")
    assert result.status == "passed", result.log_tail
    assert result.has_compile_commands and result.artifact


def test_silent_kernel_finishes_with_retry(tmp_path: Path):
    """不打印的死循环内核必须重试一次，并在一分钟内返回。"""
    directory = tmp_path / "silent"
    tiny_kernel(directory, 'void main(void) { for (;;) __asm__ volatile("wfe"); }\n')
    project = project_for(directory)
    work, logs = tmp_path / "work", tmp_path / "logs"
    built = build(project, directory, work, logs)
    assert built.status == "passed", built.log_tail
    started = time.monotonic()
    result = run(project, work, built, logs)
    assert result.status == "failed" and not result.booted
    assert result.tried_gic == [2, 3] and "NO_OUTPUT" in result.anomalies
    assert time.monotonic() - started < 60


def test_synthetic_storm_is_bounded(tmp_path: Path):
    """自写故障内核持续刷串口时识别异常、截断并按时结束。"""
    directory = tmp_path / "storm"
    tiny_kernel(directory, '''void main(void) {
    volatile unsigned int *uart = (volatile unsigned int *)0x09000000;
    const char *message = "synthetic exception\\n";
    for (;;) {
        for (const char *p = message; *p; ++p) {
            while (uart[6] & (1u << 5)) {}
            uart[0] = (unsigned char)*p;
        }
    }
}
''')
    project = project_for(directory)
    work, logs = tmp_path / "work", tmp_path / "logs"
    built = build(project, directory, work, logs)
    assert built.status == "passed", built.log_tail
    started = time.monotonic()
    result = run(project, work, built, logs)
    assert result.status == "failed" and result.booted
    assert set(result.anomalies) == {"EXC_STORM", "OUTPUT_TRUNCATED"}
    assert result.output_bytes > 256 * 1024
    assert Path(result.log_file).stat().st_size <= 256 * 1024
    assert time.monotonic() - started < 30


def test_timeout_leaves_no_container(tmp_path: Path):
    """超时返回后 Docker 中不能残留本次执行的容器。"""
    name = "ke-timeout-test-" + secrets.token_hex(4)
    started = time.monotonic()
    result = sandbox.run_in_sandbox(["sleep", "100"], tmp_path, 5, name=name,
                                    stdin_steps=[(100, "unused\n")])
    assert result.timed_out and result.exit_code is None
    assert time.monotonic() - started < 10
    listing = subprocess.run(["docker", "ps", "-a", "-q", "--filter", f"name={name}"],
                             capture_output=True, text=True, timeout=5, check=True)
    assert listing.stdout.strip() == ""


def test_executor_bounds_output_and_preserves_raw_bytes(tmp_path: Path):
    """超过缓冲上限仍持续排空管道，完整计数并保留原始空字符。"""
    result = sandbox.run_in_sandbox(
        ["python3", "-c", "import os; os.write(1, b'A\\x00B' + b'x' * 500000)"],
        tmp_path, 10, name="ke-output-test", max_output=1024,
    )
    assert result.exit_code == 0 and not result.timed_out
    assert result.output.startswith("A\x00B") and len(result.output.encode()) == 1024
    assert result.output_bytes == 500003 and result.truncated


def test_executor_is_non_root(tmp_path: Path):
    """实际容器不能以 root 身份运行学生命令。"""
    result = sandbox.run_in_sandbox(["id", "-u"], tmp_path, 10, name="ke-uid-test")
    assert result.exit_code == 0 and int(result.output.strip()) != 0


def test_build_timeout_stops_cmake(tmp_path: Path, monkeypatch):
    """CMake 配置卡死同样受编译总超时约束。"""
    directory = tmp_path / "stuck"
    directory.mkdir()
    (directory / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.12)\nproject(Stuck NONE)\nexecute_process(COMMAND sleep 100)\n")
    monkeypatch.setattr(config, "BUILD_TIMEOUT_S", 2)
    started = time.monotonic()
    result = build(project_for(directory), directory, tmp_path / "work", tmp_path / "logs")
    assert result.status == "failed" and result.errors >= 1
    assert any(d.message == "编译超时" for d in result.diagnostics)
    assert time.monotonic() - started < 10
