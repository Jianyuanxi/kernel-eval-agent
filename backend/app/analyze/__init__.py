"""块 4：clang 静态分析。scan 签名已冻结。"""
from pathlib import Path

from app.schemas import Project, ScanResult
from .scanner import run_scan


def scan(project: Project, project_dir: Path, work_dir: Path, log_dir: Path) -> ScanResult:
    """在沙箱内逐个扫描 C 文件并返回结构化告警。"""
    return run_scan(project, project_dir, work_dir, log_dir)
