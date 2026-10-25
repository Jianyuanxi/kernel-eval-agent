"""不依赖 Docker 的编译诊断与构建边界测试。"""
import json
from pathlib import Path

import pytest

from app import config
from app.buildrun import build, sandbox
from app.buildrun.compiler import find_artifact, parse_diagnostics
from app.schemas import BuildResult, ExecResult
from .conftest import project_for


def test_contract_diagnostics():
    """真实契约日志的警告计数和编号必须与示例相符。"""
    expected = BuildResult.model_validate_json((config.EXAMPLES_DIR / "build_result.json").read_text())
    actual, warnings, errors = parse_diagnostics(expected.log_tail)
    assert (warnings, errors) == (expected.warnings, expected.errors)
    assert [d.model_dump() for d in actual] == [d.model_dump() for d in expected.diagnostics]


def test_diagnostic_limit_preserves_total_counts():
    """证据上限不应导致实际警告和错误漏计。"""
    text = "\n".join(f"/workspace/src/main.c:{i + 1}:2: warning: warning {i}" for i in range(110))
    text += "\n/workspace/src/main.c:120:3: fatal error: broken header"
    diagnostics, warnings, errors = parse_diagnostics(text)
    assert len(diagnostics) == 100
    assert (warnings, errors) == (110, 1)
    assert [d.evidence_id for d in diagnostics] == [f"B{i}" for i in range(1, 101)]


def test_external_paths_and_fatal_errors():
    """越出工程根的诊断不能被计入学生工程警告。"""
    output = (
        "/workspace/../outside.c:1:2: warning: external\n"
        "/workspace/src/中文.c:2:3: fatal error: missing\n"
        "/opt/toolchain/bin/aarch64-none-elf-ld: warning: RWX\n"
    )
    diagnostics, warnings, errors = parse_diagnostics(output)
    assert (warnings, errors) == (0, 1)
    assert diagnostics[0].path == "" and not diagnostics[0].in_project
    assert diagnostics[1].path == "src/中文.c" and diagnostics[1].severity == "error"
    assert diagnostics[2].line is None


@pytest.mark.parametrize("artifact", ["miniEuler", "miniEuler.elf", "nested/other.elf"])
def test_find_artifact(tmp_path: Path, artifact: str):
    """课程常见产物和其他 ELF 都可定位为相对路径。"""
    path = tmp_path / "build" / artifact
    path.parent.mkdir(parents=True)
    path.write_bytes(b"ELF")
    assert find_artifact(tmp_path) == f"build/{artifact}"


def test_artifact_priority_and_escape(tmp_path: Path):
    """优先选择规定名称，拒绝指向工作目录外的产物。"""
    work = tmp_path / "work"
    (work / "build").mkdir(parents=True)
    outside = tmp_path / "outside.elf"
    outside.write_bytes(b"ELF")
    (work / "build/miniEuler").symlink_to(outside)
    assert find_artifact(work) is None
    (work / "build/miniEuler.elf").write_bytes(b"ELF")
    (work / "build/z.elf").write_bytes(b"ELF")
    assert find_artifact(work) == "build/miniEuler.elf"


def test_fragment_does_not_start_sandbox(tmp_path: Path, monkeypatch):
    """代码片段直接返回不支持，不访问工作目录或 Docker。"""
    def unexpected(*args, **kwargs):
        raise AssertionError("不应准备或执行片段工程")
    monkeypatch.setattr(sandbox, "prepare_workspace", unexpected)
    monkeypatch.setattr(sandbox, "run_in_sandbox", unexpected)
    result = build(project_for(tmp_path, buildable=False), tmp_path, tmp_path / "work", tmp_path / "logs")
    assert result.status == "unsupported"


@pytest.mark.parametrize("source", ["src", "."])
def test_build_success(tmp_path: Path, monkeypatch, source: str):
    """构建工作副本且保留产物、编译命令和工具链改写记录。"""
    project_dir, work, logs = (tmp_path / name for name in ("project", "work", "logs"))
    cmake = project_dir / source / "CMakeLists.txt"
    cmake.parent.mkdir(parents=True)
    original = "set(TOOLCHAIN_PATH /old/toolchain)\n"
    cmake.write_text(original)
    def execute(cmd, directory, timeout, **kwargs):
        assert directory == work and timeout == config.BUILD_TIMEOUT_S
        assert f"cmake -S {source}" in cmd[-1] and "-j2" in cmd[-1]
        assert "CMAKE_EXPORT_COMPILE_COMMANDS=ON" in cmd[-1]
        (work / "build").mkdir()
        (work / "build/miniEuler").write_bytes(b"ELF")
        (work / "build/compile_commands.json").write_text("[]")
        return ExecResult(exit_code=0, timed_out=False, output="built", output_bytes=5,
                          truncated=False, duration_s=0.01)
    monkeypatch.setattr(sandbox, "run_in_sandbox", execute)
    result = build(project_for(project_dir), project_dir, work, logs)
    assert result.status == "passed" and result.artifact == "build/miniEuler"
    assert result.has_compile_commands and result.toolchain_rewritten
    assert cmake.read_text() == original
    assert Path(result.log_file).read_text() == "built"
    assert BuildResult.model_validate(json.loads(result.model_dump_json())) == result


@pytest.mark.parametrize("exit_code,timed_out", [(1, False), (0, False), (None, True)])
def test_build_failure_and_timeout(tmp_path: Path, monkeypatch, exit_code, timed_out):
    """退出失败、缺产物和超时都不能被误报为编译通过。"""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    text = "/workspace/src/main.c:1:2: error: invalid token\n" + "x" * 4000
    monkeypatch.setattr(sandbox, "run_in_sandbox", lambda *args, **kwargs: ExecResult(
        exit_code=exit_code, timed_out=timed_out, output=text, output_bytes=900000,
        truncated=True, duration_s=1,
    ))
    result = build(project_for(project_dir), project_dir, tmp_path / "work", tmp_path / "logs")
    assert result.status == "failed"
    assert result.errors == (2 if timed_out else 1)
    assert result.diagnostics[0].path == "src/main.c"
    assert "900000" in Path(result.log_file).read_text()
    assert len(result.log_tail) == 3000
    if timed_out:
        assert result.diagnostics[-1].message == "编译超时"


def test_sandbox_error_propagates(tmp_path: Path, monkeypatch):
    """Docker 故障交由流水线处理，不能冒充学生编译错误。"""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    def broken(*args, **kwargs):
        raise sandbox.SandboxError("Docker unavailable")
    monkeypatch.setattr(sandbox, "run_in_sandbox", broken)
    with pytest.raises(sandbox.SandboxError):
        build(project_for(project_dir), project_dir, tmp_path / "work", tmp_path / "logs")
