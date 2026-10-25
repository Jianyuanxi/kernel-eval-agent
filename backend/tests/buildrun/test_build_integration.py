"""必须在 Linux Docker 沙箱中实际执行的编译验收。"""
import shutil
import time
from pathlib import Path

import pytest

from app.buildrun import build
from .conftest import project_for

pytestmark = pytest.mark.sandbox


@pytest.mark.parametrize("name,artifact", [
    ("样例1_完整工程", "build/miniEuler"),
    ("样例4_完整工程", "build/miniEuler.elf"),
])
def test_complete_sample_builds(sample_root: Path, tmp_path: Path, name: str, artifact: str):
    """两份完整工程应能产出规定名称的内核和编译命令。"""
    directory = sample_root / name
    if not directory.is_dir():
        pytest.skip(f"没有{name}")
    result = build(project_for(directory), directory, tmp_path / "work", tmp_path / "logs")
    assert result.status == "passed", result.log_tail
    assert result.artifact == artifact
    assert result.has_compile_commands and result.toolchain_rewritten


def test_invalid_source_reports_location(sample1: Path, tmp_path: Path):
    """源代码首行损坏后返回真实错误位置，原始样例不变。"""
    directory = tmp_path / "broken"
    shutil.copytree(sample1, directory)
    main = directory / "src/main.c"
    main.write_text("@@ invalid C @@\n" + main.read_text(encoding="utf-8", errors="replace"))
    started = time.monotonic()
    result = build(project_for(directory), directory, tmp_path / "work", tmp_path / "logs")
    assert result.status == "failed"
    assert any(d.path == "src/main.c" and d.severity == "error" for d in result.diagnostics)
    assert time.monotonic() - started < 200
