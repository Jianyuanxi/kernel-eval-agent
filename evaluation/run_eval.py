"""逐个植入已知缺陷，比较 clang 与完整系统相对基线的检出率。"""
import argparse
import json
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import yaml


def _same_location(item: dict, other: dict) -> bool:
    """比较两个报告条目是否指向相同文件及邻近行号。"""
    return item.get("path") == other.get("path") and abs(item.get("line", -100) - other.get("line", 100)) <= 3


def _is_new(item: dict, baseline: list[dict], *, clang: bool) -> bool:
    """过滤基线中已有的同类告警或缺陷。"""
    kind = "defect_type" if clang else "type"
    detail = "message" if clang else "title"
    return not any(
        _same_location(item, old) and item.get(kind) == old.get(kind)
        and item.get(detail) == old.get(detail) for old in baseline
    )


def _zip_sample(source: Path, archive: Path) -> None:
    """把一份样例压缩为可供上传的独立工程。"""
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not path.is_symlink() and ".git" not in path.parts and "build" not in path.parts:
                output.write(path, arcname=f"{source.name}/{path.relative_to(source).as_posix()}")


def _evaluate(client: httpx.Client, base: str, source: Path) -> dict:
    """上传工程、启动评测、轮询直到取得完整报告。"""
    with tempfile.TemporaryDirectory(prefix="ke-upload-") as temp:
        archive = Path(temp) / f"{source.name}.zip"
        _zip_sample(source, archive)
        with archive.open("rb") as stream:
            response = client.post(f"{base}/api/tasks", files={"files": (archive.name, stream, "application/zip")})
        response.raise_for_status()
        task = response.json()
    if task["stage"] != "waiting_select" or not task.get("projects"):
        raise RuntimeError(f"上传后无法选择工程：{task.get('error') or task.get('stage')}")
    project_id = task["projects"][0]["project_id"]
    task_id = task["task_id"]
    response = client.post(f"{base}/api/tasks/{task_id}/start", json={"project_id": project_id})
    response.raise_for_status()
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        response = client.get(f"{base}/api/tasks/{task_id}")
        response.raise_for_status()
        task = response.json()
        if task["stage"] == "done":
            report = client.get(f"{base}/api/tasks/{task_id}/report")
            report.raise_for_status()
            return report.json()
        if task["stage"] == "failed":
            raise RuntimeError(f"评测任务 {task_id} 失败：{task.get('error') or task.get('progress')}")
        time.sleep(2)
    raise TimeoutError(f"评测任务 {task_id} 超过 20 分钟")


def _score(item: dict, report: dict, baseline: dict) -> tuple[bool, bool, str]:
    """按文件、行号和具体缺陷类型判定新增检出。"""
    clang_hits = [
        f for f in report["scan"]["findings"]
        if _same_location(f, item) and f.get("defect_type") == item["type"]
        and _is_new(f, baseline["scan"]["findings"], clang=True)
    ]
    accepted = {item["type"], *item.get("accept_types", [])}
    system_hits = [
        d for d in report["defects"]
        if _same_location(d, item) and d.get("type") in accepted
        and _is_new(d, baseline["defects"], clang=False)
    ]
    title = system_hits[0]["title"] if system_hits else ""
    return bool(clang_hits), bool(system_hits), title


def _markdown(rows: list[tuple[str, str, bool, bool, str]]) -> str:
    """输出不含样例源码的对比统计表。"""
    clang_count = sum(row[2] for row in rows)
    system_count = sum(row[3] for row in rows)
    lines = [
        "# 创新点 A：植入缺陷检出率对比",
        "",
        "| 编号 | 类型 | clang 检出 | 完整系统检出 | 报告标题 |",
        "|---|---|---|---|---|",
    ]
    for identifier, kind, clang, system, title in rows:
        safe_title = title.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {identifier} | {kind} | {'是' if clang else '否'} | {'是' if system else '否'} | {safe_title} |")
    total = len(rows)
    lines.append(f"| 合计 | {total} | {clang_count}/{total}（{clang_count/total:.0%}） | "
                 f"{system_count}/{total}（{system_count/total:.0%}） | |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """按命令行路径执行基线和十次独立植入评测。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="后端 URL，例如 http://127.0.0.1:8000")
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    truth = yaml.safe_load(args.truth.read_text(encoding="utf-8"))
    if not isinstance(truth, list) or len(truth) != 10:
        raise ValueError("truth.yaml 必须恰好包含 10 个独立缺陷")
    with httpx.Client(timeout=120) as client:
        health = client.get(f"{base}/api/health")
        health.raise_for_status()
        mocked = set(health.json().get("mock_modules", []))
        if mocked:
            raise RuntimeError(f"服务仍使用假模块 {sorted(mocked)}；不能把假报告计入真实检出率")
        baselines = {}
        baseline_dir = args.out.parent / ".baselines"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        for sample in sorted({item["sample"] for item in truth}):
            source = args.samples / sample
            if not source.is_dir():
                raise FileNotFoundError(source)
            baselines[sample] = _evaluate(client, base, source)
            (baseline_dir / f"{sample}.json").write_text(
                json.dumps(baselines[sample], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        rows = []
        for item in truth:
            patch = args.patches / item["patch"]
            if not patch.is_file():
                raise FileNotFoundError(patch)
            with tempfile.TemporaryDirectory(prefix=f"ke-eval-{item['id']}-") as temp:
                copy = Path(temp) / item["sample"]
                shutil.copytree(args.samples / item["sample"], copy)
                subprocess.run(["git", "apply", "--check", str(patch.resolve())], cwd=copy, check=True, timeout=10)
                subprocess.run(["git", "apply", str(patch.resolve())], cwd=copy, check=True, timeout=10)
                report = _evaluate(client, base, copy)
            clang, system, title = _score(item, report, baselines[item["sample"]])
            rows.append((item["id"], item["type"], clang, system, title))
            print(f"{item['id']}: clang={clang}, system={system}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_markdown(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
