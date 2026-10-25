"""编译运行测试共用的匿名样例与工程描述。"""
from pathlib import Path

import pytest

from app import config
from app.schemas import Project


def project_for(directory: Path, *, buildable: bool = True) -> Project:
    """为本块测试构造符合冻结接口的工程描述。"""
    return Project(
        project_id="p1", name=directory.name, root=".", kind="full" if buildable else "fragment",
        arch="aarch64", buildable=buildable,
        file_count=sum(p.is_file() for p in directory.rglob("*")),
        c_files=sum(1 for _ in directory.rglob("*.c")),
        has_run_script=(directory / "runMiniEuler.sh").is_file(),
    )


@pytest.fixture
def sample_root() -> Path:
    """返回本地或服务器配置的样例目录。"""
    return config.SAMPLES_ROOT


@pytest.fixture
def sample1(sample_root: Path) -> Path:
    """取得主要演示样例，CI 无样例时按契约跳过。"""
    path = sample_root / "样例1_完整工程"
    if not (path / "src/CMakeLists.txt").is_file():
        pytest.skip("没有样例 1")
    return path
