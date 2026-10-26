"""安全展开上传文件、过滤无关文件并识别工程。"""
import fnmatch
import os
import shutil
import stat
import tempfile
import zipfile
import zlib
from pathlib import Path

from app import config
from app.schemas import IngestResult, Project
from app.schemas.common import ErrorInfo
from .source import PathInvalidError, project_files, relative_path


class _UploadError(ValueError):
    """携带上传失败的契约错误码。"""
    def __init__(self, code: str, message: str):
        """保存错误码和用户可读说明。"""
        super().__init__(message)
        self.code = code


def _ignored(path: Path) -> bool:
    """判断目录和文件名是否属于过滤规则。"""
    directories = {".git", "__MACOSX", ".vscode", ".idea", "build", "node_modules"}
    patterns = ("*.o", "*.obj", "*.a", "*.so", "*.elf", "*.bin", "*.img", "*.exe",
                "*.dll", "*.map", "*.zip", "*.rar", "*.7z", "*.tar*")
    return (any(p in directories or fnmatch.fnmatchcase(p, "cmake-build-*") for p in path.parts[:-1])
            or path.name in {".DS_Store", "Thumbs.db"}
            or any(fnmatch.fnmatchcase(path.name.lower(), p) for p in patterns))


def _zip_name(info: zipfile.ZipInfo) -> str:
    """修复未设置 UTF-8 标志位的 UTF-8 或 GBK 文件名。"""
    if info.flag_bits & 0x800:
        return info.orig_filename
    raw = info.orig_filename.encode("cp437")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk")


def _unpack(uploads: list[Path], destination: Path) -> int:
    """边读取边累计所有文件的字节数，过滤文件也受总量限制。"""
    total = count = ignored = 0
    seen: set[str] = set()
    spellings: dict[str, str] = {}

    def store(name: str, stream, size: int) -> None:
        """流式读取一个条目，超限立即停止，最多暂存 1MB。"""
        nonlocal total, count, ignored
        relative = relative_path(name)
        for length in range(1, len(relative.parts) + 1):
            prefix = "/".join(relative.parts[:length])
            folded = prefix.casefold()
            if folded in spellings and spellings[folded] != prefix:
                raise PathInvalidError("上传含大小写冲突的目录或文件")
            spellings[folded] = prefix
        key = relative.as_posix().casefold()
        if (key in seen or any(key.startswith(existing + "/") or existing.startswith(key + "/")
                               for existing in seen)):
            raise PathInvalidError("上传含重复或大小写冲突的路径")
        seen.add(key)
        count += 1
        if count > config.UNPACK_MAX_FILES:
            raise _UploadError("UPLOAD_TOO_LARGE", "解压后的文件数超过限制")
        skip = _ignored(relative) or size > 1024 * 1024
        data = bytearray()
        length = 0
        while chunk := stream.read(65536):
            total += len(chunk)
            length += len(chunk)
            if total > config.UNPACK_MAX_BYTES:
                raise _UploadError("UPLOAD_TOO_LARGE", "解压后的总大小超过限制")
            if length > 1024 * 1024:
                skip = True
                data.clear()
            if not skip:
                data.extend(chunk)
        if skip:
            ignored += 1
            return
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    if len(uploads) == 1 and uploads[0].suffix.lower() == ".zip":
        with zipfile.ZipFile(uploads[0]) as archive:
            for info in archive.infolist():
                name = _zip_name(info)
                relative_path(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise PathInvalidError("压缩包不能包含链接或特殊文件")
                if info.flag_bits & 1:
                    raise _UploadError("UPLOAD_BAD_ZIP", "不支持加密压缩包")
                if info.is_dir():
                    continue
                with archive.open(info) as stream:
                    store(name, stream, info.file_size)
    else:
        for upload in uploads:
            if upload.suffix.lower() not in {".c", ".h"}:
                raise _UploadError("UPLOAD_BAD_TYPE", "只接受 zip 或 C 源文件与头文件")
            with upload.open("rb") as stream:
                store(upload.name, stream, upload.stat().st_size)
    return ignored


def _projects(unpacked: Path, destination: Path, upload_name: str) -> tuple[list[Project], int]:
    """按目录层级识别完整工程，否则生成一个片段工程。"""
    files = project_files(unpacked)
    c_files = [p for p in files if p.suffix.lower() == ".c"]
    if not c_files:
        raise _UploadError("NO_SOURCE_FOUND", "过滤后没有 C 源文件")
    candidates = {unpacked}
    for path in files:
        candidates.update(parent for parent in path.parents if parent.is_relative_to(unpacked))
    roots = []
    for directory in sorted(candidates, key=lambda p: (len(p.parts), p.as_posix())):
        if any(directory.is_relative_to(root) for root in roots):
            continue
        cmake = directory / "CMakeLists.txt"
        if ((directory / "src" / "CMakeLists.txt").is_file()
                or (cmake.is_file() and "project(" in cmake.read_text(encoding="utf-8", errors="replace"))):
            roots.append(directory)
    kind = "full" if roots else "fragment"
    if not roots:
        roots = [Path(os.path.commonpath([str(p.parent) for p in c_files]))]
    projects = []
    included = set()
    for index, root in enumerate(sorted(roots, key=lambda p: p.relative_to(unpacked).as_posix()), 1):
        members = [p for p in files if p.is_relative_to(root)]
        included.update(members)
        arch = "unknown"
        for path in members:
            if path.name == "CMakeLists.txt" or path.suffix.lower() in {".s", ".ld", ".c"}:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
                if any(marker in text for marker in ("aarch64", "armv8", "cortex-a")):
                    arch = "aarch64"
                    break
                if "riscv" in text:
                    arch = "riscv64"
        pid = f"p{index}"
        target = destination / pid
        target.mkdir()
        for path in members:
            output = target / path.relative_to(root)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
        projects.append(Project(project_id=pid, name=Path(upload_name).stem if root == unpacked else root.name,
                                root=root.relative_to(unpacked).as_posix(), kind=kind, arch=arch,
                                buildable=kind == "full" and arch == "aarch64", file_count=len(members),
                                c_files=sum(p.suffix.lower() == ".c" for p in members),
                                has_run_script=(root / "runMiniEuler.sh").is_file(),
                                note="只有代码片段，无法编译运行" if kind == "fragment" else ""))
    return projects, len(set(files) - included)


def ingest_upload(task_dir: Path, upload_paths: list[Path], upload_name: str) -> IngestResult:
    """在临时目录处理上传，成功后发布工程，失败返回错误码。"""
    ignored = 0
    try:
        base = task_dir.resolve()
        upload_root = (base / "upload").resolve()
        for path in upload_paths:
            if path.is_symlink() or not path.resolve().is_relative_to(upload_root) or not path.is_file():
                raise PathInvalidError("上传文件必须位于任务 upload 目录内")
        if (base / "unpacked").exists() or (base / "projects").exists():
            raise _UploadError("INTERNAL_ERROR", "任务已有处理结果，不能覆盖")
        with tempfile.TemporaryDirectory(prefix=".ingest-", dir=base) as staging:
            staging = Path(staging)
            unpacked, projects_dir = staging / "unpacked", staging / "projects"
            unpacked.mkdir()
            projects_dir.mkdir()
            ignored = _unpack(upload_paths, unpacked)
            projects, outside = _projects(unpacked, projects_dir, upload_name)
            unpacked.rename(base / "unpacked")
            projects_dir.rename(base / "projects")
        return IngestResult(status="passed", upload_name=upload_name, projects=projects,
                            ignored_count=ignored + outside)
    except PathInvalidError:
        error = ErrorInfo(code="UPLOAD_UNSAFE_PATH", message="上传包含不安全的路径、链接或重复文件")
    except _UploadError as exc:
        error = ErrorInfo(code=exc.code, message=str(exc))
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError, EOFError, zlib.error):
        error = ErrorInfo(code="UPLOAD_BAD_ZIP", message="压缩包损坏、加密或使用不支持的编码")
    except OSError:
        error = ErrorInfo(code="INTERNAL_ERROR", message="无法读取上传文件或创建工程目录")
    return IngestResult(status="failed", upload_name=upload_name, ignored_count=ignored, error=error)
