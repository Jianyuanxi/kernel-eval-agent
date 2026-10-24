"""工程整理、源码读取及本地样例的验收测试。"""
import stat
import struct
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.ingest import PathInvalidError, ingest_upload, list_files, read_source
from app.main import app


def archive_task(tmp_path: Path, entries: dict) -> tuple[Path, Path]:
    """创建只含合成内容的任务上传包。"""
    task = tmp_path / "task"
    upload = task / "upload"
    upload.mkdir(parents=True)
    archive = upload / "demo.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return task, archive


def ingest(tmp_path: Path, entries: dict):
    """创建并处理测试包。"""
    task, archive = archive_task(tmp_path, entries)
    return task, ingest_upload(task, [archive], archive.name)


@pytest.mark.parametrize("name", ["../evil.c", "/evil.c", "C:/evil.c", "C:evil.c",
                                   "..\\evil.c", "//host/share/evil.c", "file.c:stream",
                                   "NUL.c", "dir./evil.c"])
def test_unsafe_paths(tmp_path, name):
    """跨平台路径逃逸和 Windows 别名均失败且不发布结果。"""
    task, result = ingest(tmp_path, {"safe.c": "int x;", name: "int y;"})
    assert result.error.code == "UPLOAD_UNSAFE_PATH"
    assert not (task / "projects").exists()
    assert not (task / "unpacked").exists()
    assert not list(task.glob(".ingest-*"))
    assert not (tmp_path / "evil.c").exists()


def test_zip_symlink(tmp_path):
    """拒绝 zip 符号链接，即使它位于被过滤目录中。"""
    info = zipfile.ZipInfo(".git/link.c")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    _, result = ingest(tmp_path, {info: "../outside.c"})
    assert result.error.code == "UPLOAD_UNSAFE_PATH"


@pytest.mark.parametrize("mode", ["broken", "encrypted", "bad_crc"])
def test_bad_zip(tmp_path, mode):
    """损坏、加密和 CRC 不匹配返回压缩包错误。"""
    task, archive = archive_task(tmp_path, {"main.c": "unique payload"})
    data = bytearray(archive.read_bytes())
    if mode == "broken":
        data = b"not a zip"
    elif mode == "encrypted":
        struct.pack_into("<H", data, 6, 1)
        central = data.index(b"PK\x01\x02")
        struct.pack_into("<H", data, central + 8, 1)
    else:
        data[data.index(b"unique payload")] ^= 1
    archive.write_bytes(data)
    result = ingest_upload(task, [archive], "demo.zip")
    assert result.status == "failed" and result.error.code == "UPLOAD_BAD_ZIP"


@pytest.mark.parametrize("encoding", ["gbk", "utf-8"])
def test_unflagged_chinese_name(tmp_path, encoding):
    """未标记 UTF-8 的中文名称按 UTF-8、GBK 顺序恢复。"""
    name = "创新功能实现.md"
    encoded = name.encode(encoding)
    placeholder = "x" * len(encoded)
    task, archive = archive_task(tmp_path, {"main.c": "int x;", placeholder: "说明"})
    archive.write_bytes(archive.read_bytes().replace(placeholder.encode(), encoded))
    result = ingest_upload(task, [archive], "demo.zip")
    assert result.status == "passed"
    assert (task / "projects/p1" / name).read_text(encoding="utf-8") == "说明"


@pytest.mark.parametrize("limit,value,entries", [
    ("UNPACK_MAX_BYTES", 3, {"main.c": "1234"}),
    ("UNPACK_MAX_BYTES", 3, {"build/ignored.o": "1234", "main.c": "x"}),
    ("UNPACK_MAX_FILES", 1, {"main.c": "x", "build/ignored.o": "y"}),
])
def test_unpack_limits(tmp_path, monkeypatch, limit, value, entries):
    """被过滤的内容仍受文件数和字节总量限制。"""
    monkeypatch.setattr(config, limit, value)
    task, result = ingest(tmp_path, entries)
    assert result.error.code == "UPLOAD_TOO_LARGE"
    assert not (task / "projects").exists()


def test_filters(tmp_path):
    """完整覆盖过滤目录、文件后缀和大文件规则。"""
    excluded = [f"{d}/x.c" for d in [".git", "__MACOSX", ".vscode", ".idea", "build", "cmake-build-debug", "node_modules"]]
    excluded += [".DS_Store", "Thumbs.db"]
    excluded += ["a" + s for s in [".o", ".obj", ".a", ".so", ".elf", ".bin", ".img", ".exe", ".dll", ".map", ".zip", ".rar", ".7z", ".tar.gz"]]
    entries = {name: "x" for name in excluded}
    entries.update({"main.c": "int x;", "big.md": b"x" * (1024 * 1024 + 1), "limit.md": b"x" * (1024 * 1024)})
    task, result = ingest(tmp_path, entries)
    assert result.status == "passed" and result.ignored_count == len(excluded) + 1
    assert [p.path for p in list_files(task / "projects/p1", "p1").files] == ["limit.md", "main.c"]


def test_no_source(tmp_path):
    """只有头文件或 C 文件全部被过滤时不能生成工程。"""
    _, result = ingest(tmp_path, {"a.h": "x", "build/main.c": "x"})
    assert result.error.code == "NO_SOURCE_FOUND"


def test_loose_sources(tmp_path):
    """直接上传三个 C 文件形成一个片段工程。"""
    upload = tmp_path / "upload"
    upload.mkdir()
    paths = [upload / f"part{i}.c" for i in range(3)]
    for p in paths:
        p.write_text("// riscv\n", encoding="utf-8")
    result = ingest_upload(tmp_path, paths, "sources")
    p = result.projects[0]
    assert (p.root, p.kind, p.arch, p.c_files, p.buildable) == (".", "fragment", "riscv64", 3, False)


def test_projects_order_and_nested_roots(tmp_path):
    """抑制子工程识别并按根路径字典序分配编号。"""
    _, result = ingest(tmp_path, {"z/src/CMakeLists.txt": "project(nested)", "z/src/main.c": "aarch64",
                                "a/CMakeLists.txt": "project(a)", "a/main.c": "riscv",
                                "outside.md": "ignored"})
    assert [(p.project_id, p.root) for p in result.projects] == [("p1", "a"), ("p2", "z")]
    assert [p.arch for p in result.projects] == ["riscv64", "aarch64"]
    assert result.ignored_count == 1


def test_fragment_common_parent(tmp_path):
    """没有 CMake 工程时使用所有 C 文件的公共父目录。"""
    _, result = ingest(tmp_path, {"demo/a/main.c": "x", "demo/b/other.c": "x", "demo/include/a.h": "x"})
    assert len(result.projects) == 1
    assert result.projects[0].root == "demo"
    assert result.projects[0].file_count == 3


def test_case_collision(tmp_path):
    """重复或大小写碰撞的文件不允许静默覆盖。"""
    _, result = ingest(tmp_path, {"main.c": "x", "MAIN.C": "y"})
    assert result.error.code == "UPLOAD_UNSAFE_PATH"


@pytest.mark.parametrize("name,lang", [("a.c", "c"), ("a.h", "h"), ("a.S", "asm"), ("a.s", "asm"),
                                         ("CMakeLists.txt", "cmake"), ("a.cmake", "cmake"),
                                         ("a.sh", "shell"), ("a.ld", "ld"), ("a.lds", "ld"),
                                         ("a.md", "markdown"), ("a.txt", "other")])
def test_languages(tmp_path, name, lang):
    """文件清单按契约识别语言。"""
    (tmp_path / name).write_bytes(b"x\r\ny")
    result = list_files(tmp_path, "p1")
    assert result.total == 1
    assert (result.files[0].lang, result.files[0].lines, result.files[0].size) == (lang, 2, 4)


@pytest.mark.parametrize("content,count", [(b"", 0), (b"\n", 1), (b"a", 1), (b"a\n", 1),
                                          (b"a\n\n", 2), (b"a\rb\x0bc", 1)])
def test_line_count(tmp_path, content, count):
    """仅 LF 划分行，末尾换行不产生额外行。"""
    (tmp_path / "a.c").write_bytes(content)
    assert list_files(tmp_path, "p1").files[0].lines == count


def test_read_source_bounds(tmp_path):
    """验证行号格式、200 行限制、截断和替换解码。"""
    (tmp_path / "main.c").write_bytes(b"\xff\r\n" + b"line\r\n" * 249)
    result = read_source(tmp_path, "main.c", -1, 999)
    assert (result.start_line, result.end_line, result.total_lines, result.evidence_id) == (1, 200, 250, "")
    assert result.text.startswith("    1 | \ufffd\n    2 | line")
    assert len(result.text.split("\n")) == 200
    result = read_source(tmp_path, "main.c", 249, 999)
    assert result.end_line == 250
    for start, end in [(251, 999), (3, 1)]:
        with pytest.raises(PathInvalidError):
            read_source(tmp_path, "main.c", start, end)


@pytest.mark.parametrize("path", ["../outside.c", "/outside.c", "C:/outside.c", "..\\outside.c", "dir", "missing.c", "binary.c", "empty.c"])
def test_read_source_invalid(tmp_path, path):
    """目录、空文件、二进制和不安全路径都拒绝读取。"""
    (tmp_path / "dir").mkdir()
    (tmp_path / "binary.c").write_bytes(b"x\x00y")
    (tmp_path / "empty.c").touch()
    with pytest.raises(PathInvalidError):
        read_source(tmp_path, path, 1, 20)


@pytest.fixture(params=[1, 2, 3, 4], ids=lambda n: f"sample-{n}")
def sample_archive(request, tmp_path):
    """本地样例临时打包，缺少样例时按项目规则跳过。"""
    number = request.param
    roots = sorted(config.SAMPLES_ROOT.glob(f"样例{number}_*"))
    if not roots:
        pytest.skip(f"本地未配置样例 {number}")
    archive = tmp_path / f"sample{number}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in roots[0].rglob("*"):
            if path.is_file():
                z.write(path, path.relative_to(roots[0]).as_posix())
    return number, archive


def check_sample(result, number):
    """对照四份样例的公开验收数字，不保存样例代码。"""
    assert result.status == "passed", result.error
    assert len(result.projects) == (11 if number == 2 else 1)
    if number == 3:
        p = result.projects[0]
        assert (p.kind, p.arch, p.buildable) == ("fragment", "riscv64", False)
    else:
        assert all((p.kind, p.arch, p.buildable) == ("full", "aarch64", True) for p in result.projects)
    if number == 1:
        p = result.projects[0]
        assert (p.file_count, p.c_files, p.has_run_script) == (50, 15, True)
    if number == 2:
        assert {p.name for p in result.projects} == {"lab1", "lab2", "lab2_hw1", "lab4", "lab5", "lab5_pro", "lab6", "lab6_pro", "lab8", "lab9", "lab10"}
    if number == 4:
        assert (result.projects[0].file_count, result.projects[0].c_files) == (61, 19)


def test_real_samples(sample_archive, tmp_path):
    """验证四份真实样例的工程识别、文件数和架构。"""
    number, archive = sample_archive
    task = tmp_path / "task"
    upload = task / "upload"
    upload.mkdir(parents=True)
    target = upload / archive.name
    target.write_bytes(archive.read_bytes())
    result = ingest_upload(task, [target], target.name)
    check_sample(result, number)
    if number == 1:
        assert (task / "projects/p1/创新功能实现.md").is_file()
    for p in result.projects:
        assert list_files(task / "projects" / p.project_id, p.project_id).total == p.file_count


def test_api_real_ingest(sample_archive, monkeypatch):
    """通过实际上传 API 和任务查询验证工程列表，其他模块仍为 mock。"""
    from app.schemas import IngestResult
    number, archive = sample_archive
    monkeypatch.setattr(config, "MOCK_MODULES", {"buildrun", "analyze", "diff", "agent", "scoring"})
    with TestClient(app) as client:
        response = client.post("/api/tasks", files={"files": (archive.name, archive.read_bytes(), "application/zip")})
        assert response.status_code == 200, response.text
        info = response.json()
        assert info["stage"] == "waiting_select", info
        fetched = client.get(f"/api/tasks/{info['task_id']}").json()
        assert fetched["projects"] == info["projects"]
        check_sample(IngestResult(status="passed", upload_name=archive.name, projects=info["projects"]), number)


@pytest.mark.parametrize("entries", [{"a.c": "x", "a.c/child.c": "y"},
                                     {"a.c/child.c": "y", "a.c": "x"}])
def test_file_directory_collision(tmp_path, entries):
    """文件与目录的路径冲突统一按不安全路径返回。"""
    _, result = ingest(tmp_path, entries)
    assert result.error.code == "UPLOAD_UNSAFE_PATH"


def test_read_resolved_escape(tmp_path, monkeypatch):
    """解析后的目标即使名义上在工程内也不能越界。"""
    original = Path.resolve
    target = tmp_path / "link.c"
    outside = tmp_path.parent / "outside.c"
    monkeypatch.setattr(Path, "resolve", lambda self, **kw: outside if self == target else original(self, **kw))
    with pytest.raises(PathInvalidError):
        read_source(tmp_path, "link.c", 1, 20)


def test_pipeline_with_real_ingest_and_diff(sample_archive, monkeypatch):
    """四份样例走真实整理和对比，验证报告落盘及差异工具返回。"""
    from app.core import pipeline, storage
    from app.schemas import DiffResult
    if not config.REF_ROOT.is_dir():
        pytest.skip("本地未配置参考代码")
    number, archive = sample_archive
    monkeypatch.setattr(config, "MOCK_MODULES", {"buildrun", "analyze", "agent", "scoring"})
    # 同步运行真实流水线，避免此测试留下后台队列任务。
    monkeypatch.setattr(pipeline, "submit", pipeline.run_pipeline)
    client = TestClient(app)
    response = client.post("/api/tasks", files={"files": (archive.name, archive.read_bytes(), "application/zip")})
    assert response.status_code == 200
    info = response.json()
    tid, pid = info["task_id"], info["projects"][0]["project_id"]
    started = client.post(f"/api/tasks/{tid}/start", json={"project_id": pid})
    assert started.status_code == 200
    task = client.get(f"/api/tasks/{tid}").json()
    assert task["stage"] == "done", task.get("error")
    response = client.get(f"/api/tasks/{tid}/report")
    assert response.status_code == 200
    report = response.json()
    diff = report["diff"]
    saved = storage.read_model(storage.TaskPaths(tid, pid).result("diff"), DiffResult)
    assert saved.model_dump() == diff
    if number == 3:
        assert diff["status"] == "unsupported"
    else:
        assert diff["status"] == "passed"
    if number in (1, 4):
        assert (diff["same"], diff["modified"], diff["added"]) == ((14, 26, 10) if number == 1 else (49, 9, 3))
    tool = client.post("/tools/diff_reference", headers={"X-Tool-Token": config.TOOL_TOKEN},
                       json={"task_id": tid, "project_id": pid})
    assert tool.status_code == 200
    assert tool.json()["baseline"] == diff["baseline"]
    assert tool.json()["modified"] == diff["modified"]
    assert all(f["change"] != "same" for f in tool.json()["files"])
