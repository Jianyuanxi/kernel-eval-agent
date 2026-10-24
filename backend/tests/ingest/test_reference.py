"""参考基线、差异范围、标记和真实样例验收。"""
import json
import zipfile
from pathlib import Path

import pytest

from app import config
from app.ingest import change_flags, diff_reference, ingest_upload
from app.schemas import DiffResult, Project
from app.schemas.ingest import FileChange


@pytest.fixture
def project() -> Project:
    """最小的合成工程元信息。"""
    return Project(project_id="p1", name="demo", root=".", kind="full", arch="aarch64",
                   buildable=True, file_count=1, c_files=1, has_run_script=False)


def put(root: Path, name: str, content: bytes) -> None:
    """写入合成测试文件，不使用任何真实样例内容。"""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.mark.parametrize("kind", ["missing", "empty", "not_lab", "no_overlap"])
def test_unsupported(tmp_path, project, kind):
    """缺参考或没有路径交集时返回不支持而非错误。"""
    ref, stu = tmp_path / "ref", tmp_path / "stu"
    put(stu, "main.c", b"main")
    if kind == "empty":
        ref.mkdir()
    elif kind == "not_lab":
        put(ref, "lab_notes/main.c", b"main")
    elif kind == "no_overlap":
        put(ref, "lab1/other.c", b"other")
    result = diff_reference(project, stu, ref)
    assert result.status == "unsupported" and result.note and result.error is None
    assert result.ref_commit == config.REF_COMMIT
    assert result.baseline is None
    if kind == "no_overlap":
        assert result.candidates == {"lab1": 0}


def test_baseline_numeric_tie_and_path_count(tmp_path, project):
    """候选按同路径数量匹配，同分选择数字编号较大的实验。"""
    stu, ref = tmp_path / "stu", tmp_path / "ref"
    put(stu, "src/main.c", b"x")
    for lab in ["lab2", "lab8", "lab10"]:
        put(ref, f"{lab}/src/main.c", b"y")
    put(ref, "lab11/other/main.c", b"x")
    result = diff_reference(project, stu, ref)
    assert result.baseline == "lab10"
    assert result.candidates == {"lab2": 1, "lab8": 1, "lab10": 1, "lab11": 0}
    put(stu, "extra.c", b"z")
    put(ref, "lab2/extra.c", b"z")
    assert diff_reference(project, stu, ref).baseline == "lab2"


@pytest.mark.parametrize("reference,student,kind,added,removed,hunks", [
    (b"a\r\nb \t\r\n\r\n", b"a\nb\n", "same", 0, 0, []),
    (b"a\nb\nc\n", b"a\nB\nc\n", "modified", 1, 1, [(2, 2)]),
    (b"a\nb\n", b"a\nnew\nb\n", "modified", 1, 0, [(2, 2)]),
    (b"a\nb\nc\n", b"a\nc\n", "modified", 0, 1, []),
    (b"a\n", b"", "modified", 0, 1, []),
    (b"", b"a\nb", "modified", 2, 0, [(1, 2)]),
    (b"\xff\n", b"\xff\r\n", "same", 0, 0, []),
    (b"  a\n", b"a\n", "modified", 1, 1, [(1, 1)]),
])
def test_normalized_opcodes(tmp_path, project, reference, student, kind, added, removed, hunks):
    """归一化保留行内与行首语义，差异区间使用学生侧行号。"""
    stu, ref = tmp_path / "stu", tmp_path / "ref"
    put(stu, "main.c", student)
    put(ref, "lab1/main.c", reference)
    result = diff_reference(project, stu, ref)
    f = result.files[0]
    assert (f.change, f.added_lines, f.removed_lines) == (kind, added, removed)
    assert [(h.start, h.end) for h in f.hunks] == hunks
    assert f.evidence_id == ("" if kind == "same" else "D1")


def test_added_empty_and_evidence_order(tmp_path, project):
    """新增空文件没有无效的 1..0 区间，证据只给新增和修改。"""
    stu, ref = tmp_path / "stu", tmp_path / "ref"
    for name, data in [("z.c", b"z\n\n"), ("a.c", b""), ("b.c", b"same"), ("c.c", b"new")]:
        put(stu, name, data)
    put(ref, "lab1/b.c", b"same")
    put(ref, "lab1/c.c", b"old")
    put(ref, "lab1/deleted.c", b"not returned")
    result = diff_reference(project, stu, ref)
    assert (result.same, result.modified, result.added) == (1, 1, 2)
    assert [(f.path, f.evidence_id) for f in result.files] == [("a.c", "D1"), ("b.c", ""), ("c.c", "D2"), ("z.c", "D3")]
    assert result.files[0].hunks == [] and result.files[0].added_lines == 0
    assert result.files[-1].hunks[0].model_dump() == {"start": 1, "end": 1}
    assert DiffResult.model_validate(result.model_dump()) == result


def test_binary_files_not_reported_as_same(tmp_path, project):
    """二进制参与路径匹配但不伪造文本比较结果。"""
    stu, ref = tmp_path / "stu", tmp_path / "ref"
    put(stu, "main.c", b"same")
    put(ref, "lab1/main.c", b"same")
    put(stu, "blob.dat", b"\x00binary")
    put(stu, "different.dat", b"text")
    put(ref, "lab1/different.dat", b"\x00binary")
    result = diff_reference(project, stu, ref)
    assert result.candidates == {"lab1": 2}
    assert [f.path for f in result.files] == ["main.c"]
    assert "2" in result.note
    assert change_flags(result, "blob.dat", 1) == (None, False)


def test_read_error(tmp_path, project, monkeypatch):
    """参考读取失败返回 error，不冒充学生代码问题。"""
    stu, ref = tmp_path / "stu", tmp_path / "ref"
    put(stu, "main.c", b"x")
    put(ref, "lab1/main.c", b"x")
    def fail(self):
        """模拟磁盘读取失败。"""
        raise PermissionError("synthetic")
    monkeypatch.setattr(Path, "read_bytes", fail)
    result = diff_reference(project, stu, ref)
    assert result.status == "error" and result.error.code == "INTERNAL_ERROR"


@pytest.mark.parametrize("status", [None, "unsupported", "error"])
def test_flags_unavailable(status):
    """无可用对比时保持未知。"""
    result = DiffResult(status=status) if status else None
    assert change_flags(result, "a.c", 1) == (None, False)


@pytest.mark.parametrize("kind,line,expected", [("same", 1, (False, True)),
    ("modified", 1, (False, False)), ("modified", 2, (True, False)), ("modified", 3, (True, False)),
    ("modified", 4, (False, False)), ("added", 2, (True, False)), ("added", 4, (False, False))])
def test_flags_closed_ranges(kind, line, expected):
    """改动区间两端均包含，same 单独标记为基线未变。"""
    result = DiffResult(status="passed", files=[FileChange(path="a.c", change=kind, hunks=[{"start": 2, "end": 3}])])
    assert change_flags(result, "a.c", line) == expected
    assert change_flags(result, "missing.c", line) == (None, False)


@pytest.fixture(params=[1, 3, 4], ids=lambda n: f"sample-{n}")
def real_diff(request, tmp_path):
    """实际整理本地样例后与配置指定的参考代码比较。"""
    number = request.param
    roots = sorted(config.SAMPLES_ROOT.glob(f"样例{number}_*"))
    if not roots or not config.REF_ROOT.is_dir():
        pytest.skip(f"本地缺少样例 {number} 或参考代码")
    task = tmp_path / "task"
    upload = task / "upload"
    upload.mkdir(parents=True)
    archive = upload / "sample.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in roots[0].rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(roots[0]).as_posix())
    ingested = ingest_upload(task, [archive], archive.name)
    assert ingested.status == "passed"
    project = ingested.projects[0]
    return number, diff_reference(project, task / "projects" / project.project_id, config.REF_ROOT)


def test_real_diff(real_diff):
    """真实样例统计与样例 1 的完整契约逐字段一致。"""
    number, result = real_diff
    if number == 3:
        assert result.status == "unsupported" or all(n == 0 for n in result.candidates.values())
        assert result.error is None
        return
    assert result.status == "passed" and result.baseline == "lab10"
    assert (result.same, result.modified, result.added) == ((14, 26, 10) if number == 1 else (49, 9, 3))
    if number == 1:
        expected = json.loads((config.EXAMPLES_DIR / "diff_result.json").read_text(encoding="utf-8"))
        assert result.model_dump() == expected
        assert change_flags(result, "src/main.c", 56) == (True, False)
        assert change_flags(result, "src/main.c", 57) == (True, False)
        assert change_flags(result, "src/bsp/vsnprintf_s.c", 1) == (False, True)
        assert next(f for f in result.files if f.path == "src/shell/shmsg.c").change == "added"
