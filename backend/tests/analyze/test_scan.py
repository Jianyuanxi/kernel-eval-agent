"""静态分析的纯函数及沙箱验收测试。"""
import json
import plistlib
from pathlib import Path

import pytest

from app import config
from app.analyze import scan
from app.analyze.scanner import extract_arguments, finalize_findings, map_checker, parse_plist
from app.schemas import ExecResult, Finding, Project, ScanResult


def project_for(directory: Path, *, kind: str = "full", arch: str = "aarch64") -> Project:
    """构造符合冻结接口的样例描述。"""
    return Project(
        project_id="p1", name=directory.name, root=".", kind=kind, arch=arch,
        buildable=kind == "full" and arch == "aarch64",
        file_count=sum(p.is_file() for p in directory.rglob("*")),
        c_files=sum(1 for _ in directory.rglob("*.c")),
        has_run_script=(directory / "runMiniEuler.sh").is_file(),
    )


def test_extract_arguments():
    """保留分开和合并写法的预处理参数，丢弃 gcc 专有选项。"""
    entry = {
        "directory": "/workspace/build",
        "command": "aarch64-none-elf-gcc -I ../src/include -D NAME=1 -include ../src/config.h "
                   "-isystem /opt/toolchain/include -std=gnu11 -mcpu=cortex-a53 -O2 -Werror -c ../src/main.c",
    }
    assert extract_arguments(entry) == [
        "-I", "/workspace/src/include", "-D", "NAME=1",
        "-include", "/workspace/src/config.h", "-isystem", "/opt/toolchain/include", "-std=gnu11",
    ]
    args = extract_arguments({"directory": "/workspace", "arguments": ["cc", "-Iinc", "-DFOO", "-std=c99"]})
    assert args == ["-I/workspace/inc", "-DFOO", "-std=c99"]


@pytest.mark.parametrize("checker,message,kind", [
    ("core.NullDereference", "bad", "NULL_DEREF"),
    ("core.NonNullParamChecker", "bad", "NULL_DEREF"),
    ("nullability.NullablePassedToNonnull", "bad", "NULL_DEREF"),
    ("core.CallAndMessage", "null argument", "NULL_DEREF"),
    ("core.CallAndMessage", "uninitialized value", "UNINIT_VAR"),
    ("core.DivideZero", "bad", "DIV_ZERO"),
    ("core.uninitialized.Assign", "bad", "UNINIT_VAR"),
    ("core.UndefinedBinaryOperatorResult", "bad", "UNINIT_VAR"),
    ("core.StackAddressEscape", "bad", "WILD_POINTER"),
    ("core.StackAddrEscapeBase", "bad", "WILD_POINTER"),
    ("alpha.security.ArrayBoundV2", "bad", "OUT_OF_BOUNDS"),
    ("security.ArrayBound", "bad", "OUT_OF_BOUNDS"),
    ("alpha.unix.cstring.OutOfBounds", "bad", "OUT_OF_BOUNDS"),
    ("unix.Malloc", "Use of memory after it is freed", "USE_AFTER_FREE"),
    ("unix.MallocSizeof", "Use of memory after", "USE_AFTER_FREE"),
    ("cplusplus.NewDelete", "Use of memory after", "USE_AFTER_FREE"),
    ("unix.Malloc", "Attempt to free released memory", "DOUBLE_FREE"),
    ("unix.Malloc", "Potential leak", "MEM_LEAK"),
    ("deadcode.DeadStores", "bad", "UNUSED"),
    ("security.insecureAPI.strcpy", "bad", "OTHER_MINOR"),
    ("core.SomeOtherChecker", "bad", "OTHER_NORMAL"),
    ("custom.Checker", "bad", None),
])
def test_checker_mapping(checker: str, message: str, kind: str | None):
    """评分规则的每行和具有多分支的检查器均有独立用例。"""
    actual, severity = map_checker(checker, message)
    assert actual == kind
    assert (severity is None) == (kind is None)


def test_plist_and_deduplication():
    """头文件越界诊断会被丢弃，同一路径、行和检查器只编号一次。"""
    data = plistlib.dumps({
        "files": ["/workspace/src/main.c", "/opt/toolchain/include/stdint.h", "/workspace/../outside.c"],
        "diagnostics": [
            {"check_name": "core.NullDereference", "description": "null", "location": {"file": 0, "line": 12, "col": 4}},
            {"check_name": "core.NullDereference", "description": "null again", "location": {"file": 0, "line": 12, "col": 5}},
            {"check_name": "deadcode.DeadStores", "description": "unused", "location": {"file": 0, "line": 3, "col": 2}},
            {"check_name": "core.NullDereference", "description": "bad", "location": {"file": 1, "line": 2, "col": 1}},
            {"check_name": "core.NullDereference", "description": "bad", "location": {"file": 2, "line": 2, "col": 1}},
        ],
    })
    findings, count = finalize_findings(parse_plist(data))
    assert count == 2
    assert [(f.evidence_id, f.path, f.line, f.defect_type) for f in findings] == [
        ("C1", "src/main.c", 3, "UNUSED"), ("C2", "src/main.c", 12, "NULL_DEREF"),
    ]


def test_fragment_failure_is_unsupported(tmp_path: Path, monkeypatch):
    """缺头文件导致全部失败时不能误报为零缺陷。"""
    source = tmp_path / "project"
    source.mkdir()
    (source / "a.c").write_text('#include "missing.h"\nint x;\n', encoding="utf-8")
    def fake_run(cmd, work_dir, timeout_s, **kwargs):
        assert cmd[0] == "clang"
        assert "--target=riscv64-unknown-elf" in cmd
        return ExecResult(exit_code=1, timed_out=False, output="a.c:1:10: error: missing.h not found",
                          output_bytes=40, truncated=False, duration_s=0.01)
    monkeypatch.setattr("app.buildrun.sandbox.run_in_sandbox", fake_run)
    result = scan(project_for(source, kind="fragment", arch="riscv64"), source, tmp_path / "work", tmp_path / "logs")
    assert result.status == "unsupported" and result.coverage == 0
    assert result.files_total == 1 and result.files_scanned == 0
    assert result.files_failed[0].path == "a.c"
    assert result.files_failed[0].reason == "error: missing.h not found"
    assert Path(result.log_file).is_file()


def test_full_mode_falls_back_when_cmake_fails(tmp_path: Path, monkeypatch):
    """CMake 配置失败时仍以 full 模式使用片段参数扫描。"""
    source = tmp_path / "project"
    (source / "src").mkdir(parents=True)
    (source / "src/a.c").write_text("int f(void) { return 1; }\n", encoding="utf-8")
    (source / "src/CMakeLists.txt").write_text("broken", encoding="utf-8")
    def fake_run(cmd, work_dir, timeout_s, **kwargs):
        if cmd[0] == "cmake":
            return ExecResult(exit_code=1, timed_out=False, output="config failed",
                              output_bytes=13, truncated=False, duration_s=0.01)
        plist = {"files": ["/workspace/src/a.c"], "diagnostics": []}
        (work_dir / "out/1.plist").write_bytes(plistlib.dumps(plist))
        assert ["-I", "/workspace"] == cmd[-3:-1]
        return ExecResult(exit_code=0, timed_out=False, output="",
                          output_bytes=0, truncated=False, duration_s=0.01)
    monkeypatch.setattr("app.buildrun.sandbox.run_in_sandbox", fake_run)
    result = scan(project_for(source), source, tmp_path / "work", tmp_path / "logs")
    assert result.mode == "full" and result.status == "passed"
    assert result.files_scanned == 1 and result.findings_total == 0


@pytest.mark.sandbox
def test_sample1_scan(tmp_path: Path):
    """样例 1 应重现 14/15 个文件和 7 条告警。"""
    source = config.SAMPLES_ROOT / "样例1_完整工程"
    if not source.is_dir():
        pytest.skip("没有样例 1")
    result = scan(project_for(source), source, tmp_path / "work", tmp_path / "logs")
    ScanResult.model_validate(result.model_dump())
    assert result.status == "passed"
    assert (result.files_total, result.files_scanned, result.findings_total) == (15, 14, 7)
    assert any(f.path.endswith("prt_sched_single.c") for f in result.files_failed)
    assert any(f.path == "src/main.c" and f.line == 57 and f.defect_type == "UNUSED" for f in result.findings)
    assert sum(f.path == "src/bsp/vsnprintf_s.c" and f.defect_type == "NULL_DEREF" for f in result.findings) == 6


@pytest.mark.sandbox
def test_sample3_scan(tmp_path: Path):
    """片段样例因缺头文件应全部失败。"""
    source = config.SAMPLES_ROOT / "样例3_代码片段"
    if not source.is_dir():
        pytest.skip("没有样例 3")
    result = scan(project_for(source, kind="fragment", arch="riscv64"), source, tmp_path / "work", tmp_path / "logs")
    assert result.status == "unsupported" and result.coverage == 0 and result.files_failed


@pytest.mark.sandbox
def test_sample4_scan(tmp_path: Path):
    """第二份完整工程至少应成功扫描一个文件。"""
    source = config.SAMPLES_ROOT / "样例4_完整工程"
    if not source.is_dir():
        pytest.skip("没有样例 4")
    result = scan(project_for(source), source, tmp_path / "work", tmp_path / "logs")
    assert result.status == "passed" and result.files_scanned > 0


@pytest.mark.sandbox
def test_small_null_deref(tmp_path: Path):
    """自制片段中的显式空指针解引用应有 clang 证据。"""
    source = tmp_path / "project"
    source.mkdir()
    (source / "bug.c").write_text("int f(void) { int *p = 0; return *p; }\n", encoding="utf-8")
    result = scan(project_for(source, kind="fragment"), source, tmp_path / "work", tmp_path / "logs")
    assert result.status == "passed"
    assert any(f.defect_type == "NULL_DEREF" for f in result.findings)



def test_full_mode_uses_compile_database(tmp_path: Path, monkeypatch):
    """完整工程应沿用编译数据库的头文件与宏参数。"""
    source = tmp_path / "project"
    (source / "src/include").mkdir(parents=True)
    (source / "src/main.c").write_text("int f(void) { return 1; }\n", encoding="utf-8")
    (source / "src/CMakeLists.txt").write_text("project(test C)", encoding="utf-8")
    def fake_run(cmd, work_dir, timeout_s, **kwargs):
        if cmd[0] == "cmake":
            (work_dir / "build").mkdir()
            (work_dir / "build/compile_commands.json").write_text(json.dumps([{
                "directory": "/workspace/build", "file": "/workspace/src/main.c",
                "arguments": ["gcc", "-I", "../src/include", "-D", "FLAG=1", "-mcpu=cortex-a53", "-c", "../src/main.c"],
            }]), encoding="utf-8")
        else:
            assert cmd[0] == "clang"
            assert ["-I", "/workspace/src/include"] == cmd[cmd.index("-I"):cmd.index("-I") + 2]
            assert ["-D", "FLAG=1"] == cmd[cmd.index("-D"):cmd.index("-D") + 2]
            assert not any(arg.startswith("-mcpu") for arg in cmd)
            (work_dir / "out/1.plist").write_bytes(plistlib.dumps({
                "files": ["/workspace/src/main.c"],
                "diagnostics": [{"check_name": "core.DivideZero", "description": "Division by zero",
                                 "location": {"file": 0, "line": 1, "col": 4}}],
            }))
        return ExecResult(exit_code=0, timed_out=False, output="", output_bytes=0,
                          truncated=False, duration_s=0.01)
    monkeypatch.setattr("app.buildrun.sandbox.run_in_sandbox", fake_run)
    result = scan(project_for(source), source, tmp_path / "work", tmp_path / "logs")
    assert result.status == "passed" and result.files_scanned == 1
    assert result.findings[0].defect_type == "DIV_ZERO"
