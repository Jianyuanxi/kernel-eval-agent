"""不依赖 QEMU 的命令提取、运行结果和串口证据测试。"""
from pathlib import Path

import pytest

from app import config
from app.buildrun import run, sandbox
from app.buildrun.runner import detect_gic, extract_commands, feature_hints, normalize_output, split_output
from app.schemas import BuildResult, ExecResult, RunResult
from .conftest import project_for


def executed(output: str = "", *, truncated: bool = False) -> ExecResult:
    """构造正常结束窗口的沙箱输出。"""
    return ExecResult(exit_code=124, timed_out=False, output=output,
                      output_bytes=len(output.encode()), truncated=truncated, duration_s=0.1)


def kernel(work: Path) -> BuildResult:
    """为模拟运行准备有效的工作目录内产物。"""
    path = work / "build/miniEuler"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"ELF")
    return BuildResult(status="passed", artifact="build/miniEuler")


def test_gic_script_precedes_source(tmp_path: Path):
    """脚本最后一个参数优先于源码注释，缺省版本为二。"""
    assert detect_gic(tmp_path) == 2
    source = tmp_path / "src/config.h"
    source.parent.mkdir()
    source.write_text("// gic-version=3\n")
    assert detect_gic(tmp_path) == 3
    source.write_text("#define GIC_VERSION 3\n")
    assert detect_gic(tmp_path) == 3
    script = tmp_path / "runMiniEuler.sh"
    script.write_text("qemu -machine virt,gic-version=3\nqemu -machine virt,gic-version=2\n")
    assert detect_gic(tmp_path) == 2


def test_command_sources_and_order(tmp_path: Path):
    """三种课程命令定义方式按源码顺序提取并去重。"""
    source = tmp_path / "src/shell/commands.c"
    source.parent.mkdir(parents=True)
    source.write_text('strcmp(cmd, "tick"); strncmp(cmd, "mem", 3); {"help", handler}; '
                      "if(cmd[0]=='p' && cmd[1]=='s') {} "
                      'strcmp(cmd, "info"); strcmp(cmd, "overflow");')
    assert extract_commands(tmp_path) == ["top", "tick", "mem", "help", "ps", "info"]


def test_character_comparisons_require_contiguous_indices(tmp_path: Path):
    """乱序下标和其他目录中的字符串不应被拼成命令。"""
    source = tmp_path / "src/kernel/shell/commands.c"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\xff if (cmd[0]=='x' && cmd[2]=='y') {}")
    (tmp_path / "src/other.c").write_text('strcmp(cmd, "ignore");')
    assert extract_commands(tmp_path) == ["top", "tick"]


def test_source_links_cannot_read_host_files(tmp_path: Path):
    """即使构建期间新建了链接，后续分析也不能读取宿主文件。"""
    work = tmp_path / "work"
    (work / "src/shell").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text('gic-version=3\nstrcmp(cmd, "private");')
    (work / "runMiniEuler.sh").symlink_to(outside)
    (work / "src/shell/commands.c").symlink_to(outside)
    assert detect_gic(work) == 2
    assert extract_commands(work) == ["top", "tick"]


def test_sample1_character_commands(sample1: Path):
    """真实样例逐字符定义的 mem 命令必须被发现。"""
    assert extract_commands(sample1) == ["top", "tick", "mem"]


def test_contract_output_and_feature_hints():
    """按真实契约重建串口输出后，证据和功能提示应一致。"""
    expected = RunResult.model_validate_json((config.EXAMPLES_DIR / "run_result.json").read_text())
    raw = expected.boot_output
    for command in expected.commands:
        raw += expected.shell_prompt + command.command + "\r\n" + command.output.replace("\n", "\r\n\r\n") + "\r\n"
    raw += expected.shell_prompt + "\rqemu-system-aarch64: terminating on signal 15\n"
    boot, prompt, commands = split_output(raw, [c.command for c in expected.commands])
    assert boot == expected.boot_output
    assert prompt == expected.shell_prompt
    assert commands == expected.commands
    assert feature_hints(True, commands) == expected.feature_hints


def test_unconfirmed_prompt_and_output_limits():
    """只有命令回显才能确认提示符，启动和命令输出分别限长。"""
    assert split_output("Welcome # banner\nbooted", ["top"])[1] is None
    boot, prompt, commands = split_output("b" * 4500 + "\nmini # top\n" + "x" * 4500, ["top"])
    assert len(boot) == 4000 and prompt == "mini # " and len(commands[0].output) == 4000
    assert normalize_output("A\r\n\r\nB\rC\x00\n\n") == "A\nB\nC\n"


@pytest.mark.parametrize("status", ["failed", "unsupported", "skipped", "error"])
def test_unbuilt_project_is_skipped(tmp_path: Path, monkeypatch, status: str):
    """编译未通过时不触发 Docker，也不产生运行日志。"""
    def unexpected(*args, **kwargs):
        raise AssertionError("不应执行")
    monkeypatch.setattr(sandbox, "run_in_sandbox", unexpected)
    result = run(project_for(tmp_path), tmp_path, BuildResult(status=status), tmp_path / "logs")
    assert result.status == "skipped" and not (tmp_path / "logs").exists()


def test_retry_ignores_qemu_messages(tmp_path: Path, monkeypatch):
    """QEMU 自身输出不算启动，第二个 GIC 成功时保留两次日志。"""
    built = kernel(tmp_path)
    outputs = iter([executed("qemu-system-aarch64: no serial output\n"), executed("AArch64 Bare Metal\n")])
    calls = []
    def execute(cmd, work, timeout, **kwargs):
        calls.append(cmd)
        assert timeout == config.RUN_WINDOW_S + 10
        assert kwargs["stdin_steps"] == [(5, "top\r"), (2, "tick\r")]
        assert "-nic" in cmd and cmd[cmd.index("-nic") + 1] == "none"
        return next(outputs)
    monkeypatch.setattr(sandbox, "run_in_sandbox", execute)
    result = run(project_for(tmp_path), tmp_path, built, tmp_path / "logs")
    assert result.status == "passed" and result.booted
    assert result.tried_gic == [2, 3] and result.gic_version == 3
    assert len(calls) == 2 and result.feature_hints == ["F_UART"]
    log = Path(result.log_file).read_text()
    assert "gic-version=2" in log and "gic-version=3" in log
    assert result.output_bytes == len("qemu-system-aarch64: no serial output\nAArch64 Bare Metal\n".encode())


def test_silent_kernel_retries_once(tmp_path: Path, monkeypatch):
    """完全没有串口输出时至多尝试两个版本并返回 NO_OUTPUT。"""
    built = kernel(tmp_path)
    monkeypatch.setattr(sandbox, "run_in_sandbox", lambda *args, **kwargs: executed())
    result = run(project_for(tmp_path), tmp_path, built, tmp_path / "logs")
    assert result.status == "failed" and result.tried_gic == [2, 3]
    assert result.anomalies == ["NO_OUTPUT"] and not result.booted


@pytest.mark.parametrize("lines,storm", [(49, False), (50, True)])
def test_storm_threshold_and_truncation(tmp_path: Path, monkeypatch, lines: int, storm: bool):
    """五十次重复是刷屏阈值；截断需要独立标记。"""
    built = kernel(tmp_path)
    monkeypatch.setattr(sandbox, "run_in_sandbox", lambda *args, **kwargs: executed(
        "Catch a exception.\r\n" * lines, truncated=True,
    ))
    result = run(project_for(tmp_path), tmp_path, built, tmp_path / "logs")
    assert result.status == ("failed" if storm else "passed")
    assert ("EXC_STORM" in result.anomalies) == storm
    assert "OUTPUT_TRUNCATED" in result.anomalies and result.tried_gic == [2]


def test_artifact_escape_rejected(tmp_path: Path):
    """运行器不得把工作目录外的文件当作内核传给 QEMU。"""
    outside = tmp_path / "outside.elf"
    outside.write_bytes(b"ELF")
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(sandbox.SandboxError):
        run(project_for(work), work, BuildResult(status="passed", artifact="../outside.elf"), work / "logs")
