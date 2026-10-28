#!/usr/bin/env python3
"""一键验收 docs/06 的 S1–S11。在服务器真实模式下跑；假数据也可用来检查脚本本身。

用法：
  python acceptance/run_samples.py --base http://127.0.0.1:8000 --samples samples --out acceptance/result.md
"""
from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

SAMPLE_DIRS = {
    "1": "样例1_完整工程",
    "2": "样例2_分阶段工程",
    "3": "样例3_代码片段",
    "4": "样例4_完整工程",
}
SAMPLE2_LABS = ["lab1", "lab2", "lab2_hw1", "lab4", "lab5", "lab5_pro", "lab6", "lab6_pro", "lab8", "lab9", "lab10"]
WAIT_S = 360
POLL_S = 2


class Check:
    def __init__(self, sid: str, name: str):
        self.sid, self.name = sid, name
        self.ok = False
        self.evidence = ""


def zip_dir(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            zf.write(path, path.relative_to(src).as_posix())


def upload_zip(client: httpx.Client, zip_path: Path) -> dict:
    with zip_path.open("rb") as f:
        r = client.post("/api/tasks", files={"files": (zip_path.name, f, "application/zip")})
    r.raise_for_status()
    return r.json()


def wait_stage(client: httpx.Client, task_id: str, timeout: int = WAIT_S) -> tuple[dict, float]:
    t0 = time.monotonic()
    info = {}
    while time.monotonic() - t0 < timeout:
        info = client.get(f"/api/tasks/{task_id}").json()
        if info.get("stage") in {"done", "failed"}:
            return info, time.monotonic() - t0
        time.sleep(POLL_S)
    return info, time.monotonic() - t0


def start_named(client: httpx.Client, info: dict, name: str | None) -> dict:
    if info.get("stage") != "waiting_select":
        return info
    projects = info.get("projects") or []
    if name:
        proj = next((p for p in projects if p.get("name") == name), None)
        if proj is None:
            raise RuntimeError(f"任务 {info['task_id']} 没有名为 {name} 的工程，实际 {[p.get('name') for p in projects]}")
        pid = proj["project_id"]
    else:
        pid = projects[0]["project_id"]
    r = client.post(f"/api/tasks/{info['task_id']}/start", json={"project_id": pid})
    r.raise_for_status()
    return r.json()


def evaluate(client: httpx.Client, sample: Path, project_name: str | None = None) -> tuple[dict, dict | None, float]:
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / f"{sample.name}.zip"
        zip_dir(sample, zpath)
        info = upload_zip(client, zpath)
    info = start_named(client, info, project_name)
    info, elapsed = wait_stage(client, info["task_id"])
    report = None
    if info.get("stage") == "done":
        report = client.get(f"/api/tasks/{info['task_id']}/report").json()
    return info, report, elapsed


def sample_path(root: Path, key: str) -> Path:
    p = root / SAMPLE_DIRS[key]
    if not p.is_dir():
        raise FileNotFoundError(f"找不到样例目录 {p}")
    return p


def check_s1(client, samples: Path) -> tuple[Check, dict]:
    c = Check("S1", "样例走通")
    bits = []
    reports: dict[str, dict] = {}
    try:
        jobs = [
            ("1", sample_path(samples, "1"), None),
            ("4", sample_path(samples, "4"), None),
            ("2-lab10", sample_path(samples, "2"), "lab10"),
            ("2-lab6_pro", sample_path(samples, "2"), "lab6_pro"),
            ("3", sample_path(samples, "3"), None),
        ]
        ok = True
        for key, path, name in jobs:
            info, report, elapsed = evaluate(client, path, name)
            tid, stage = info.get("task_id"), info.get("stage")
            bits.append(f"{key} {tid} {stage} {elapsed:.1f}s")
            if stage != "done" or report is None:
                ok = False
            else:
                reports[key] = {"info": info, "report": report, "elapsed": elapsed}
        c.ok = ok
    except Exception as e:
        bits.append(str(e))
        c.ok = False
    c.evidence = "；".join(bits)
    return c, reports


def check_s2(client, samples: Path) -> Check:
    c = Check("S2", "多工程识别")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "s2.zip"
            zip_dir(sample_path(samples, "2"), zpath)
            info = upload_zip(client, zpath)
        names = sorted(p["name"] for p in info.get("projects") or [])
        c.ok = info.get("stage") == "waiting_select" and len(names) == 11 and names == sorted(SAMPLE2_LABS)
        c.evidence = f"任务 {info.get('task_id')}，{len(names)} 个工程：{names}"
    except Exception as e:
        c.evidence = str(e)
    return c


def check_s3(reports: dict) -> Check:
    c = Check("S3", "片段模式")
    item = reports.get("3")
    if not item:
        c.evidence = "样例 3 没有成功出报告"
        return c
    report = item["report"]
    compile_run = next((i for i in report["score"]["items"] if i["key"] == "compile_run"), None)
    max_sum = sum(i["max"] for i in report["score"]["items"] if i["score"] is not None)
    c.ok = (
        report.get("mode") == "fragment"
        and report.get("build") is None
        and report.get("run") is None
        and compile_run is not None
        and compile_run["score"] is None
        and abs(max_sum - 80) < 0.01
        and "coverage" in report.get("scan", {})
    )
    scan = report.get("scan") or {}
    c.evidence = (
        f"任务 {report['task_id']} mode={report.get('mode')} "
        f"build={report.get('build')} run={report.get('run')} "
        f"scan.coverage={scan.get('coverage')} 计分满分之和={max_sum} 总分={report['score']['total']}"
    )
    return c


def check_s4(reports: dict) -> Check:
    c = Check("S4", "耗时")
    parts = []
    ok = True
    if not reports:
        c.evidence = "S1 没有可统计的报告"
        return c
    for key, item in reports.items():
        elapsed = item["elapsed"]
        parts.append(f"{key} {item['report']['task_id']} {elapsed:.1f}s")
        if elapsed > 300:
            ok = False
    c.ok = ok
    c.evidence = "；".join(parts)
    return c


def check_s5(client, samples: Path, reports: dict, repeat: int) -> Check:
    c = Check("S5", "稳定")
    first = reports.get("1")
    if not first:
        c.evidence = "样例 1 第一次没有出报告"
        return c
    if repeat < 2:
        c.evidence = f"未重复（--repeat {repeat}），第一次总分 {first['report']['score']['total']}"
        c.ok = True
        return c
    info, report, elapsed = evaluate(client, sample_path(samples, "1"))
    if report is None:
        c.evidence = f"第二次失败 stage={info.get('stage')} {info.get('error')}"
        return c
    a, b = first["report"]["score"]["total"], report["score"]["total"]
    c.ok = abs(a - b) <= 5
    c.evidence = f"{first['report']['task_id']}={a}，{report['task_id']}={b}，差 {abs(a - b)}，第二次 {elapsed:.1f}s"
    return c


def check_s6(client, reports: dict) -> Check:
    c = Check("S6", "位置真实")
    bad = []
    n = 0
    for key, item in reports.items():
        report = item["report"]
        tid = report["task_id"]
        locs: list[tuple[str, int]] = []
        for feature in report.get("features") or []:
            locs.extend((loc["path"], loc["line"]) for loc in feature.get("locations") or [])
        for loc in (report.get("innovation") or {}).get("locations") or []:
            locs.append((loc["path"], loc["line"]))
        for defect in report.get("defects") or []:
            locs.append((defect["path"], defect["line"]))
        for path, line in locs:
            n += 1
            r = client.get(f"/api/tasks/{tid}/source", params={"path": path, "start": line, "end": line})
            if r.status_code != 200:
                bad.append(f"{key} {path}:{line} HTTP {r.status_code}")
                continue
            data = r.json()
            total = data.get("total_lines", 0)
            if not (1 <= line <= total):
                bad.append(f"{key} {path}:{line} total={total}")
    c.ok = n > 0 and not bad
    c.evidence = f"检查 {n} 处" + ("，全部合法" if not bad else "；" + "；".join(bad[:8]))
    return c


def check_s7(reports: dict) -> Check:
    c = Check("S7", "工具调用")
    parts = []
    ok = True
    for key, item in reports.items():
        calls = item["report"].get("tool_calls") or []
        agent = [x for x in calls if x.get("source") == "agent"]
        read_ok = any(x.get("tool") == "read_source" and x.get("status") == "passed" for x in agent)
        knowledge = any(x.get("tool") == "knowledge" for x in agent)
        parts.append(f"{key} read_source={read_ok} knowledge={knowledge} agent={len(agent)}")
        if not (read_ok and knowledge):
            ok = False
    c.ok = bool(reports) and ok
    c.evidence = "；".join(parts) or "没有报告"
    return c


def check_s8(samples: Path) -> Check:
    c = Check("S8", "检出率")
    candidates = [
        Path("evaluation/result.md"),
        Path("/opt/kernel-eval/current/evaluation/result.md"),
        Path("/data/kernel-eval/evaluation/result.md"),
        samples.parent / "evaluation" / "result.md",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        c.evidence = "块 4 的 evaluation/result.md 还不在仓库或服务器上，本项引用它"
        return c
    text = path.read_text(encoding="utf-8", errors="replace")
    sys_n = re.search(r"系统(?:检出)?\s*[：:=]?\s*(\d+)", text)
    clang_n = re.search(r"clang(?:检出)?\s*[：:=]?\s*(\d+)", text)
    numbers = [int(x) for x in re.findall(r"(\d+)\s*/\s*10", text)]
    system = int(sys_n.group(1)) if sys_n else (numbers[-1] if numbers else None)
    clang = int(clang_n.group(1)) if clang_n else (numbers[0] if numbers else None)
    c.ok = system is not None and system >= 6
    c.evidence = f"引用 {path}：系统检出 {system}，clang 检出 {clang}"
    return c


def check_s9(client, samples: Path) -> Check:
    c = Check("S9", "容错")
    bits = []
    ok = True
    try:
        r = client.post("/api/tasks", files={"files": ("note.txt", b"not source", "text/plain")})
        body = r.json()
        code = (body.get("error") or {}).get("code")
        txt_ok = code == "UPLOAD_BAD_TYPE"
        bits.append(f"txt → {code or r.status_code}")
        ok = ok and txt_ok

        r = client.post("/api/tasks", files={"files": ("bad.zip", b"not-a-zip", "application/zip")})
        body = r.json()
        zip_code = (body.get("error") or {}).get("code")
        zip_ok = zip_code == "UPLOAD_BAD_ZIP" or body.get("stage") == "failed"
        bits.append(f"坏 zip → {zip_code or body.get('stage')}")
        ok = ok and zip_ok

        src = sample_path(samples, "1")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "broken"
            shutil.copytree(src, copy)
            main = next(copy.rglob("main.c"), None)
            if main is None:
                raise RuntimeError("样例 1 没有 main.c")
            main.write_text("this is not C;\n" + main.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            info, report, elapsed = evaluate(client, copy)
            build = (report or {}).get("build") or {}
            compile_ok = info.get("stage") in {"done", "failed"} and (
                (report and (build.get("status") == "failed" or (report.get("score") or {}).get("items")))
            )
            bits.append(f"编译不过 {info.get('task_id')} {info.get('stage')} build={build.get('status')} {elapsed:.1f}s")
            ok = ok and compile_ok

            loop = Path(tmp) / "loop"
            shutil.copytree(src, loop)
            main = next(loop.rglob("main.c"))
            text = main.read_text(encoding="utf-8", errors="replace")
            patched, n = re.subn(r"(int\s+main\s*\([^;{]*\)\s*\{)", r"\1 while(1){}", text, count=1)
            if n == 0:
                patched = "int main(void){ while(1){} }\n" + text
            main.write_text(patched, encoding="utf-8")
            info, report, elapsed = evaluate(client, loop)
            loop_ok = info.get("stage") in {"done", "failed"} and elapsed < WAIT_S
            bits.append(f"死循环 {info.get('task_id')} {info.get('stage')} {elapsed:.1f}s")
            ok = ok and loop_ok
        c.ok = ok
    except Exception as e:
        bits.append(str(e))
        c.ok = False
    c.evidence = "；".join(bits)
    return c


def check_s10(client, reports: dict) -> Check:
    c = Check("S10", "追问")
    item = reports.get("1")
    if not item:
        c.evidence = "样例 1 没有报告，无法追问"
        return c
    report = item["report"]
    tid = report["task_id"]
    total = report["score"]["total"]
    idx = 0 if report.get("defects") else None
    t0 = time.monotonic()
    try:
        r = client.post(
            f"/api/tasks/{tid}/followup",
            json={"question": "请用一两句话说明这个问题为什么危险。", "defect_index": idx},
            timeout=70,
        )
        elapsed = time.monotonic() - t0
        if r.status_code != 200:
            c.evidence = f"HTTP {r.status_code} {r.text[:200]}，{elapsed:.1f}s"
            return c
        data = r.json()
        again = client.get(f"/api/tasks/{tid}/report").json()
        c.ok = bool(data.get("answer")) and elapsed <= 30 and again["score"]["total"] == total
        c.evidence = (
            f"任务 {tid} {elapsed:.1f}s 回答 {len(data.get('answer') or '')} 字，"
            f"分数 {total}→{again['score']['total']}"
        )
    except Exception as e:
        c.evidence = f"{time.monotonic() - t0:.1f}s {e}"
    return c


def check_s11(client, reports: dict) -> Check:
    c = Check("S11", "导出")
    item = reports.get("1") or (next(iter(reports.values())) if reports else None)
    if not item:
        c.evidence = "没有可导出的报告"
        return c
    tid = item["report"]["task_id"]
    js = client.get(f"/api/tasks/{tid}/export", params={"format": "json"})
    md = client.get(f"/api/tasks/{tid}/export", params={"format": "md"})
    text = md.text
    total = str(item["report"]["score"]["total"])
    c.ok = js.status_code == 200 and md.status_code == 200 and total in text and "缺陷" in text and "分" in text
    c.evidence = f"任务 {tid} json={js.status_code} md={md.status_code} 含总分 {total}"
    return c


def write_md(path: Path, checks: list[Check]) -> None:
    lines = ["# 系统验收结果", "", "| 编号 | 项目 | 结果 | 依据 |", "| --- | --- | --- | --- |"]
    for c in checks:
        lines.append(f"| {c.sid} | {c.name} | {'pass' if c.ok else 'fail'} | {c.evidence.replace('|', '/')} |")
    lines += ["", f"合计：{sum(c.ok for c in checks)}/{len(checks)} pass", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://132.232.242.186")
    p.add_argument("--samples", default="/data/kernel-eval/samples")
    p.add_argument("--out", default="acceptance/result.md")
    p.add_argument("--repeat", type=int, default=1)
    args = p.parse_args()
    samples = Path(args.samples)
    client = httpx.Client(base_url=args.base.rstrip("/"), timeout=httpx.Timeout(120.0, read=420.0))
    checks: list[Check] = []
    s1, reports = check_s1(client, samples)
    checks.append(s1)
    checks.append(check_s2(client, samples))
    checks.append(check_s3(reports))
    checks.append(check_s4(reports))
    checks.append(check_s5(client, samples, reports, args.repeat))
    checks.append(check_s6(client, reports))
    checks.append(check_s7(reports))
    checks.append(check_s8(samples))
    checks.append(check_s9(client, samples))
    checks.append(check_s10(client, reports))
    checks.append(check_s11(client, reports))
    out = Path(args.out)
    write_md(out, checks)
    print(out.read_text(encoding="utf-8"))
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
