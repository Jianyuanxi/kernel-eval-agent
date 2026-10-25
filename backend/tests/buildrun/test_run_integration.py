"""在真实 QEMU 中验证课程样例的启动、交互与异常。"""
import time
from pathlib import Path

import pytest

from app.buildrun import build, run
from .conftest import project_for

pytestmark = pytest.mark.sandbox


def test_sample1_shell(sample1: Path, tmp_path: Path):
    """演示样例返回标准提示符和 top、tick、mem 的真实输出。"""
    project = project_for(sample1)
    work, logs = tmp_path / "work", tmp_path / "logs"
    built = build(project, sample1, work, logs)
    assert built.status == "passed", built.log_tail
    result = run(project, work, built, logs)
    assert result.status == "passed" and result.booted
    assert result.shell_prompt == "miniEuler # "
    assert [c.command for c in result.commands] == ["top", "tick", "mem"]
    assert [c.evidence_id for c in result.commands] == ["R2", "R3", "R4"]
    assert result.feature_hints == ["F_UART", "F_TIMER", "F_TASK", "F_SHELL"]
    assert "\n\n" not in result.boot_output
    assert all("\n\n" not in c.output for c in result.commands)
    assert result.anomalies == []


@pytest.mark.parametrize("lab", ["lab10", "lab6_pro", "lab1"])
def test_lab_runs(sample_root: Path, tmp_path: Path, lab: str):
    """验证 GIC 三、异常刷屏和只有单行打印的基础实验。"""
    directory = sample_root / "样例2_分阶段工程" / lab
    if not directory.is_dir():
        pytest.skip(f"没有样例 2 {lab}")
    project = project_for(directory)
    work, logs = tmp_path / "work", tmp_path / "logs"
    built = build(project, directory, work, logs)
    assert built.status == "passed", built.log_tail
    started = time.monotonic()
    result = run(project, work, built, logs)
    assert result.booted
    if lab == "lab10":
        assert result.status == "passed" and result.gic_version == 3
    elif lab == "lab6_pro":
        # 该学生内核实测既可能完成任务，也可能陷入异常刷屏。
        # 用实际串口证据校验分类；确定性刷屏由自写故障内核另行严格验收。
        raw = Path(result.log_file).read_text(encoding="utf-8", errors="replace")
        assert "Lab6 Optimized" in raw
        if raw.count("Catch a exception.") >= 50:
            assert result.status == "failed" and "EXC_STORM" in result.anomalies
            assert "OUTPUT_TRUNCATED" in result.anomalies
        else:
            assert result.status == "passed" and result.anomalies == []
            assert "[Task1] Completed" in raw and "[Task2] Completed" in raw
        assert time.monotonic() - started < 30
    else:
        assert result.status == "passed" and "AArch64 Bare Metal" in result.boot_output
