"""工作副本隔离和过期容器清理的纯函数测试。"""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.buildrun import sandbox


def test_workspace_rewrites_and_discards_stale_artifacts(tmp_path: Path):
    """兼容两种工具链写法，不能复用学生带来的旧产物。"""
    source, work = tmp_path / "project", tmp_path / "work"
    source.mkdir()
    text = ('set(TOOLCHAIN_PATH "/root/old")\n'
            'set(CMAKE_C_COMPILER /opt/arm-gnu/bin/aarch64-none-elf-gcc)\n')
    (source / "CMakeLists.txt").write_text(text)
    (source / "build").mkdir()
    (source / "build/miniEuler").write_bytes(b"stale")
    assert sandbox.prepare_workspace(source, work) == ["CMakeLists.txt"]
    assert (source / "CMakeLists.txt").read_text() == text
    assert (source / "build/miniEuler").exists()
    assert not (work / "build").exists()
    assert "/opt/toolchain/bin/aarch64-none-elf-gcc" in (work / "CMakeLists.txt").read_text()


@pytest.mark.parametrize("relation", ["same", "inside", "parent"])
def test_workspace_overlap_rejected_before_deletion(tmp_path: Path, relation: str):
    """目录参数错误时应保留工程原件。"""
    source = tmp_path / "project"
    source.mkdir()
    original = source / "main.c"
    original.write_text("original")
    work = {"same": source, "inside": source / "work", "parent": tmp_path}[relation]
    with pytest.raises(sandbox.SandboxError):
        sandbox.prepare_workspace(source, work)
    assert original.read_text() == "original"


def test_workspace_symlink_rejected(tmp_path: Path):
    """学生工程中的链接不能带入工作目录外的内容。"""
    source = tmp_path / "project"
    source.mkdir()
    (source / "outside.h").symlink_to(tmp_path / "private.h")
    with pytest.raises(sandbox.SandboxError):
        sandbox.prepare_workspace(source, tmp_path / "work")


def test_cleanup_only_stale_owned_labeled_containers(monkeypatch):
    """清理不得触及新容器、其他用户或未带项目标签的容器。"""
    monkeypatch.setattr(sandbox.os, "getuid", lambda: 1000)
    now = datetime.now(timezone.utc)
    ids = [str(i) * 64 for i in range(1, 5)]
    containers = []
    for index, identifier in enumerate(ids):
        labels = {"kernel-eval": "1", "kernel-eval.owner": "1000"}
        if index == 2:
            labels["kernel-eval.owner"] = "2000"
        if index == 3:
            labels = {}
        containers.append({"Id": identifier, "Config": {"Labels": labels},
                           "State": {"Running": True, "StartedAt": (
                               now - timedelta(seconds=30 if index == 1 else 700)).isoformat()}})
    calls = []
    def execute(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "ps":
            assert "label=kernel-eval=1" in cmd and "label=kernel-eval.owner=1000" in cmd
            return subprocess.CompletedProcess(cmd, 0, "\n".join(ids), "")
        if cmd[1] == "inspect":
            return subprocess.CompletedProcess(cmd, 0, json.dumps(containers), "")
        assert cmd == ["docker", "rm", "-f", ids[0]]
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(sandbox.subprocess, "run", execute)
    assert sandbox.cleanup_stale() == [ids[0]]
    assert len(calls) == 3


def test_cleanup_reports_docker_failure(monkeypatch):
    """Docker 故障不应被误报成没有过期容器。"""
    def broken(*args, **kwargs):
        raise subprocess.TimeoutExpired("docker", 5)
    monkeypatch.setattr(sandbox.subprocess, "run", broken)
    with pytest.raises(sandbox.SandboxError):
        sandbox.cleanup_stale()


def test_executor_refuses_root(tmp_path: Path, monkeypatch):
    """防止把宿主 root 身份直接带进学生代码容器。"""
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(sandbox.os, "getuid", lambda: 0)
    with pytest.raises(sandbox.SandboxError, match="普通用户"):
        sandbox.run_in_sandbox(["id"], tmp_path, 1, name="ke-root-check")
