"""工程内的安全路径、文件清单与源码读取。"""
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.schemas import FileList, SourceSlice
from app.schemas.ingest import FileEntry


class PathInvalidError(ValueError):
    """路径不存在、越界或不是可读取的文本文件。"""


def relative_path(name: str) -> Path:
    """拒绝可跨平台越界或在 Windows 上产生别名的路径。"""
    posix, windows = PurePosixPath(name), PureWindowsPath(name)
    if (not name or "\x00" in name or "\\" in name or posix.is_absolute()
            or windows.drive or ".." in posix.parts or not posix.parts):
        raise PathInvalidError("路径必须是工程内的相对路径")
    for part in posix.parts:
        if (":" in part or any(c in part for c in '<>"|?*')
                or any(ord(c) < 32 for c in part) or part.endswith((" ", "."))
                or PureWindowsPath(part).is_reserved()):
            raise PathInvalidError("路径含不安全的文件名")
    return Path(*posix.parts)


def project_files(root: Path) -> list[Path]:
    """列出工程内普通文件，拒绝符号链接和越界路径。"""
    base = root.resolve()
    files = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            raise PathInvalidError("工程包含链接或越界路径")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def text_lines(data: bytes) -> list[str]:
    """以 LF 分行，兼容 CRLF，保留孤立 CR 和其他文本字符。"""
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if not text:
        return []
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def list_files(project_dir: Path, project_id: str) -> FileList:
    """按相对路径返回文件大小、行数和语言。"""
    languages = {".c": "c", ".h": "h", ".s": "asm", ".cmake": "cmake",
                 ".sh": "shell", ".ld": "ld", ".lds": "ld", ".md": "markdown"}
    entries = []
    for path in project_files(project_dir):
        data = path.read_bytes()
        lang = "cmake" if path.name == "CMakeLists.txt" else languages.get(path.suffix.lower(), "other")
        entries.append(FileEntry(path=path.relative_to(project_dir).as_posix(),
                                 size=len(data), lines=len(text_lines(data)), lang=lang))
    return FileList(project_id=project_id, total=len(entries), files=entries)


def read_source(project_dir: Path, path: str, start_line: int, end_line: int) -> SourceSlice:
    """安全读取最多 200 行源码，并按契约添加行号。"""
    relative = relative_path(path)
    target = (project_dir / relative).resolve()
    if not target.is_relative_to(project_dir.resolve()) or not target.is_file():
        raise PathInvalidError("文件不存在或不在工程内")
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise PathInvalidError("文件无法读取") from exc
    if b"\x00" in data:
        raise PathInvalidError("不能读取二进制文件")
    lines = text_lines(data)
    start = max(1, start_line)
    end = min(end_line, len(lines), start + 199)
    if start > len(lines) or end < start:
        raise PathInvalidError("行范围无效或超过文件末尾")
    return SourceSlice(path=relative.as_posix(), start_line=start, end_line=end,
                       total_lines=len(lines), text="\n".join(
                           f"{i:>5} | {lines[i - 1]}" for i in range(start, end + 1)))
