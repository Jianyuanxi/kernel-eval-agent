"""评测流水线：编译 → 运行 → 扫描 → 对比参考代码 → 智能体评审 → 校验 → 评分 → 报告。

必做步骤由这里保证（智能体漏调也不会漏扫）；智能体调用工具时拿到的是这里存下的结果。
单线程队列，同一时间只评一个任务。
"""
import json
import queue
import re
import threading
import time
import traceback

from pydantic import ValidationError

from app import config
from app.buildrun.sandbox import SandboxError
from app.core import mocks, modules, prompts, storage
from app.core.dify_client import DifyClient, DifyError
from app.core.storage import TaskPaths, now_iso
from app.schemas import (
    DEFECT_TYPES, AgentThought, BuildResult, DiffResult, ErrorInfo, FileEntry, Project, Report, ReportDefect,
    ReviewResult, RunResult, ScanResult, TaskInfo,
)

ACTIVE_STAGES = {"queued", "building", "running", "scanning", "diffing", "reviewing", "scoring"}
_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()


class PipelineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def submit(task_id: str, project_id: str) -> None:
    _queue.put((task_id, project_id))


def start_worker() -> None:
    threading.Thread(target=_worker, daemon=True, name="pipeline").start()


def _worker() -> None:
    while True:
        task_id, project_id = _queue.get()
        try:
            run_pipeline(task_id, project_id)
        except Exception:  # 兜底，保证队列不断
            traceback.print_exc()


def _set(info: TaskInfo, stage: str, progress: str) -> None:
    info.stage = stage  # type: ignore[assignment]
    info.progress = progress
    storage.save_task(info)


def _record(task_id: str, tool: str, status: str, t0: float, summary: str, inp: dict | None = None,
            source: str = "pipeline", evidence_ids: list[str] | None = None) -> None:
    storage.append_tool_call(task_id, {
        "source": source, "tool": tool, "input": inp or {}, "status": status,
        "started_at": now_iso(), "duration_ms": int((time.monotonic() - t0) * 1000),
        "summary": summary, "evidence_ids": evidence_ids or []})


def _call(fn, *args):
    try:
        return fn(*args)
    except NotImplementedError as e:
        raise PipelineError("INTERNAL_ERROR", f"{fn.__module__}.{fn.__name__} 还没实现；开发期可设 KE_MOCK_MODULES 用假数据") from e


def run_pipeline(task_id: str, project_id: str) -> None:
    info = storage.load_task(task_id)
    if info is None:
        return
    paths = TaskPaths(task_id, project_id)
    project = next(p for p in info.projects if p.project_id == project_id)
    try:
        report = _evaluate(info, paths, project)
        storage.write_json(paths.report, report)
        _set(info, "done", f"评测完成：{report.score.total} 分（{report.score.grade}）")
    except PipelineError as e:
        info.error = ErrorInfo(code=e.code, message=str(e))  # type: ignore[arg-type]
        _set(info, "failed", str(e))
    except Exception as e:
        traceback.print_exc()
        info.error = ErrorInfo(code="INTERNAL_ERROR", message=f"{type(e).__name__}: {e}")
        _set(info, "failed", "内部错误")


def _run_kernel(br, project: Project, paths: TaskPaths, build: BuildResult) -> RunResult:
    """在 QEMU 里跑一次内核，沙箱出错转成 error 结果"""
    try:
        return _call(br.run, project, paths.work_build, build, paths.logs)
    except SandboxError as e:
        return RunResult(status="error", error=ErrorInfo(code="SANDBOX_ERROR", message=str(e)))


def _evaluate(info: TaskInfo, paths: TaskPaths, project: Project) -> Report:
    tid = info.task_id
    br, an, ing, df = modules.get("buildrun"), modules.get("analyze"), modules.get("ingest"), modules.get("diff")
    paths.logs.mkdir(parents=True, exist_ok=True)
    full = project.buildable

    build: BuildResult | None = None
    run: RunResult | None = None
    if full:
        _set(info, "building", "正在沙箱中编译")
        t0 = time.monotonic()
        try:
            build = _call(br.build, project, paths.project, paths.work_build, paths.logs)
        except SandboxError as e:
            build = BuildResult(status="error", error=ErrorInfo(code="SANDBOX_ERROR", message=str(e)))
        build.log_file = paths.rel(build.log_file) if build.log_file else ""
        storage.write_json(paths.result("build"), build)
        _record(tid, "compile_project", build.status, t0, f"编译{_zh(build.status)}，{build.warnings} 条警告，{build.errors} 个错误")

        _set(info, "running", "正在 QEMU 中运行内核")
        t0 = time.monotonic()
        run = _run_kernel(br, project, paths, build)
        if run.status == "failed" and run.booted:  # 启动了但没进 shell：学生内核有竞争时偶发，重跑一次用新结果
            run = _run_kernel(br, project, paths, build)
        run.log_file = paths.rel(run.log_file) if run.log_file else ""
        storage.write_json(paths.result("run"), run)
        _record(tid, "run_kernel", run.status, t0, f"运行{_zh(run.status)}，{'已启动' if run.booted else '未启动'}"
                + (f"，识别到提示符 {run.shell_prompt!r}" if run.shell_prompt else ""))

    _set(info, "scanning", "正在用 clang 静态分析")
    t0 = time.monotonic()
    try:
        scan: ScanResult = _call(an.scan, project, paths.project, paths.work_scan, paths.logs)
    except SandboxError as e:
        scan = ScanResult(status="error", mode="full" if full else "fragment",
                          error=ErrorInfo(code="SANDBOX_ERROR", message=str(e)))
    _record(tid, "clang_scan", scan.status, t0,
            f"扫描 {scan.files_scanned}/{scan.files_total} 个文件，{scan.findings_total} 条告警")

    _set(info, "diffing", "正在和参考代码对比")
    t0 = time.monotonic()
    diff: DiffResult = _call(df.diff_reference, project, paths.project, config.REF_ROOT)
    storage.write_json(paths.result("diff"), diff)
    _record(tid, "diff_reference", diff.status, t0,
            f"基线 {diff.baseline or '无'}：相同 {diff.same}，修改 {diff.modified}，新增 {diff.added}")
    for f in scan.findings:
        f.in_baseline_unchanged = df.change_flags(diff, f.path, f.line)[1]
    scan.log_file = paths.rel(scan.log_file) if scan.log_file else ""
    storage.write_json(paths.result("scan"), scan)

    _set(info, "reviewing", "智能体正在评审")
    file_list = _call(ing.list_files, paths.project, project.project_id)
    targets = preload_targets({f.path: f for f in file_list.files}, diff, scan, build)
    review, conv, thoughts, model = _agent_review(info, paths, project, build, targets)
    storage.write_json(paths.result("review"), review)
    defects, warnings = _finalize_defects(tid, review, {f.path: f.lines for f in file_list.files}, diff, df,
                                          build, run, scan)

    _set(info, "scoring", "正在计算分数")
    score = _call(modules.get("scoring").compute_score, project, build, run, review, defects)
    storage.write_json(paths.result("score"), score)

    return Report(
        task_id=tid, generated_at=now_iso(), project=project, mode="full" if full else "fragment",
        build=build, run=run, scan=scan, diff=diff, summary=review.summary, features=review.features,
        defects=defects, style=review.style, innovation=review.innovation, score=score,
        tool_calls=storage.read_tool_calls(tid), agent_thoughts=thoughts, model=model,
        conversation_id=conv, warnings=warnings)


def _zh(status: str) -> str:
    return {"passed": "通过", "failed": "失败", "timeout": "超时", "skipped": "跳过",
            "unsupported": "不支持", "error": "出错"}.get(status, status)


# ---------------- 智能体评审 ----------------

TOOL_NAMES_ZH = {"knowledge": "知识库检索"}  # 写进提示词时用的名字；其余工具名原样给模型


def required_tools(project: Project, build: BuildResult | None) -> list[str]:
    req = []
    if project.buildable:
        req.append("compile_project")
        if build and build.status == "passed":
            req.append("run_kernel")
    req += ["clang_scan", "read_source", "knowledge"]
    return req


def _called_tools(task_id: str) -> set[str]:
    """智能体调过的工具。read_source 只算成功的（路径错误不算读过源码）；编译失败、扫描 unsupported 照样算调过"""
    return {r.tool for r in storage.read_tool_calls(task_id)
            if r.source == "agent" and (r.tool != "read_source" or r.status == "passed")}


def _record_knowledge(task_id: str, thoughts: list[AgentThought]) -> None:
    """知识库检索不经过我们的工具服务，从 agent_thought 里补记录（Dify 知识库工具名以 dataset_ 开头；
    同一轮并行调多个工具时 tool 是用 ; 拼起来的）"""
    for t in thoughts:
        if any(n.startswith("dataset_") for n in t.tool.split(";")):
            _record(task_id, "knowledge", "passed", time.monotonic(), f"检索知识库：{t.tool_input[:80]}", source="agent")


def _zh_tools(names: list[str]) -> str:
    return "、".join(TOOL_NAMES_ZH.get(n, n) for n in names)


# ---------------- 关键源码预读 ----------------
# 读哪些文件按规则定，评审前一次交给智能体：每次评测看到的材料相同，也省掉逐个文件来回读的十来轮。

PRELOAD_FILE_LINES = 400  # 每个文件最多预读前 400 行（两段，read_source 一段最多 200 行），后面的行只取告警附近
PRELOAD_TOTAL_LINES = 4000  # 一次评测预读总行数上限，约 5 万 tokens


def preload_targets(files: dict[str, FileEntry], diff: DiffResult, scan: ScanResult,
                    build: BuildResult | None) -> list[tuple[str, int, int]]:
    """选出要预读的源码段 (path, 起始行, 结束行)。

    顺序：有 clang/gcc 告警的文件（参考代码原样的不算）→ 学生新增的 → 学生修改的，同级按路径排；
    只取 C 源码和说明文档（.md）。没有参考代码可比时，所有 C 文件都算学生写的。
    """
    flagged: dict[str, set[int]] = {}
    for f in scan.findings:
        if not f.in_baseline_unchanged and f.path in files:
            flagged.setdefault(f.path, set()).add(f.line)
    for d in build.diagnostics if build else []:
        if d.in_project and d.line and d.path in files:
            flagged.setdefault(d.path, set()).add(d.line)
    changed = {c.path: c.change for c in diff.files if c.change != "same"}
    if not diff.files:
        changed = {p: "added" for p, e in files.items() if e.lang == "c"}

    def rank(p: str) -> tuple:
        return (p not in flagged, changed.get(p) != "added", p)

    cands = [p for p in files if files[p].lines and (p in flagged or (p in changed and files[p].lang in ("c", "markdown")))]
    out: list[tuple[str, int, int]] = []
    total = 0
    for p in sorted(cands, key=rank):
        n = files[p].lines
        segs = [(s, min(s + 199, n)) for s in range(1, min(n, PRELOAD_FILE_LINES) + 1, 200)]
        for ln in sorted(flagged.get(p, ())):
            if ln > segs[-1][1]:
                segs.append((max(segs[-1][1] + 1, ln - 20), min(n, ln + 20)))
        for s, e in segs:
            if total + e - s + 1 > PRELOAD_TOTAL_LINES:
                return out
            out.append((p, s, e))
            total += e - s + 1
    return out


def _preload(task_id: str, project_dir, targets: list[tuple[str, int, int]]) -> str:
    """按 targets 读源码，每段记一条 source=pipeline 的 read_source（分配 S 编号），返回附在第一条消息里的文本"""
    from app.ingest import PathInvalidError
    ing = modules.get("ingest")
    parts = []
    for path, s, e in targets:
        t0 = time.monotonic()
        try:
            sl = ing.read_source(project_dir, path, s, e)
        except PathInvalidError:
            continue
        rec = storage.append_tool_call(task_id, {
            "source": "pipeline", "tool": "read_source", "input": {"path": path, "start_line": s, "end_line": e},
            "status": "passed", "started_at": now_iso(), "duration_ms": int((time.monotonic() - t0) * 1000),
            "summary": f"预读 {sl.path} 第 {sl.start_line}–{sl.end_line} 行"}, new_source_evidence=True)
        parts.append(f"### {rec.evidence_ids[0]}：{sl.path} 第 {sl.start_line}–{sl.end_line} 行（全文 {sl.total_lines} 行）\n"
                     f"```\n{sl.text}\n```")
    return "\n\n".join(parts) or "（没有可预读的文件，用 list_files 看工程结构，再用 read_source 读代码。）"


def parse_review(answer: str) -> ReviewResult:
    """从回答里取出 JSON：优先 ```json 代码块，否则取第一个 { 到最后一个 }"""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", answer, re.S)
    text = m.group(1) if m else answer[answer.find("{"): answer.rfind("}") + 1]
    if not text:
        raise ValueError("回答里没有 JSON")
    return ReviewResult.model_validate(json.loads(text))


def _try_parse(answer: str) -> ReviewResult | None:
    try:
        return parse_review(answer)
    except (ValueError, ValidationError):
        return None


def _merge_knowledge(kept: ReviewResult, again: ReviewResult) -> None:
    """补查知识库后，只把新回答里同一条缺陷（位置和类型都相同）的知识点讲解换进来"""
    new = {(d.path, d.line, d.type): d.knowledge for d in again.defects if d.knowledge}
    for d in kept.defects:
        d.knowledge = new.get((d.path, d.line, d.type), d.knowledge)


def _agent_review(info: TaskInfo, paths: TaskPaths, project: Project, build: BuildResult | None,
                  targets: list[tuple[str, int, int]]):
    tid = info.task_id
    if config.is_mock("agent"):
        for r in mocks.agent_tool_calls():
            storage.append_tool_call(tid, r)
        return mocks.review(), "mock-conversation", [], "mock"

    client = DifyClient()
    user = f"task-{tid}"
    need = required_tools(project, build)
    first = [t for t in need if t != "read_source"] + ["diff_reference"]
    query = prompts.render(  # preloaded 放最后替换，学生代码里碰巧有 {task_id} 之类也不会被改
        "review_query", task_id=tid, project_id=project.project_id, project_name=project.name,
        mode="完整工程" if project.buildable else "代码片段", arch=project.arch, c_files=project.c_files,
        required_tools=_zh_tools(need), first_tools=_zh_tools(first),
        preloaded=_preload(tid, paths.project, targets))
    thoughts: list[AgentThought] = []
    deadline = time.monotonic() + config.AGENT_TIMEOUT_S  # 首次、提醒、修正共用一个总预算

    def chat(text: str, conv: str = ""):
        r = client.chat(text, user, conv, deadline=deadline)
        thoughts.extend(r.thoughts)
        _record_knowledge(tid, r.thoughts)
        return r

    try:
        res = chat(query)
        kept = _try_parse(res.answer)
        missing = [t for t in need if t not in _called_tools(tid)]
        if missing:
            res = chat(prompts.render("nudge", missing=_zh_tools(missing)), res.conversation_id)
            missing = [t for t in need if t not in _called_tools(tid)]
            if missing:
                raise PipelineError("AGENT_SKIPPED_TOOLS", f"提醒后智能体仍未调用：{_zh_tools(missing)}")
            if kept is not None:  # 提醒只为补调工具：第一次的缺陷和功能判断保留，免得整份重写又变一次
                again = _try_parse(res.answer)
                if again is not None:
                    _merge_knowledge(kept, again)
                return kept, res.conversation_id, thoughts, config.MODEL_NAME
        try:
            review = parse_review(res.answer)
        except (ValueError, ValidationError) as e:
            res = chat(prompts.render("repair", errors=str(e)[:1500]), res.conversation_id)
            try:
                review = parse_review(res.answer)
            except (ValueError, ValidationError) as e2:
                (paths.logs / "agent_answer.txt").write_text(res.answer, encoding="utf-8")
                raise PipelineError("REVIEW_INVALID", f"智能体输出两次都不符合格式：{str(e2)[:300]}") from e2
    except DifyError as e:
        raise PipelineError(e.code, str(e)) from e
    return review, res.conversation_id, thoughts, config.MODEL_NAME


# ---------------- 校验并补全缺陷 ----------------

def issued_evidence(task_id: str, build: BuildResult | None, run: RunResult | None, scan: ScanResult,
                    diff: DiffResult) -> set[str]:
    ids = {f.evidence_id for f in scan.findings} | {f.evidence_id for f in diff.files if f.evidence_id}
    if build:
        ids |= {d.evidence_id for d in build.diagnostics}
    if run:
        ids |= {run.boot_evidence_id} | {c.evidence_id for c in run.commands}
    for r in storage.read_tool_calls(task_id):
        ids |= set(r.evidence_ids)
    return ids


def _finalize_defects(task_id: str, review: ReviewResult, file_lines: dict[str, int], diff: DiffResult, df,
                      build, run, scan) -> tuple[list[ReportDefect], list[str]]:
    warnings: list[str] = []
    known = issued_evidence(task_id, build, run, scan, diff)

    def ok(path: str, line: int) -> bool:
        return 1 <= line <= file_lines.get(path, 0)

    # 功能点、创新点：去掉不存在的位置和证据，判断本身保留（判断错不错由人看报告，位置必须真实，docs/06 S6）
    for f in [*review.features, review.innovation]:
        name = getattr(f, "feature_id", "innovation")
        bad_loc = [loc for loc in f.locations if not ok(loc.path, loc.line)]
        if bad_loc:
            warnings.append(f"{name} 引用了不存在的位置 {[f'{x.path}:{x.line}' for x in bad_loc]}，已去掉")
            f.locations = [loc for loc in f.locations if ok(loc.path, loc.line)]
        ev = getattr(f, "evidence_ids", None)
        if ev and any(e not in known for e in ev):
            warnings.append(f"{name} 引用了不存在的证据 {[e for e in ev if e not in known]}，已去掉")
            f.evidence_ids = [e for e in ev if e in known]

    # clang 报过的位置，类型按 analyze 的映射表定（docs/03），模型只判断真假，不再每次换类型
    rule_type = {(f.path, f.line): f.defect_type for f in scan.findings if f.defect_type}
    seen: set[tuple[str, int, str]] = set()
    out: list[ReportDefect] = []
    for d in review.defects:
        if not ok(d.path, d.line):
            warnings.append(f"丢弃缺陷“{d.title}”：{d.path}:{d.line} 不存在")
            continue
        if (t := rule_type.get((d.path, d.line))) and t != d.type:
            d.type = t
            if d.source == "llm":
                d.source = "clang+llm"
        key = (d.path, d.line, d.type)
        if key in seen:
            warnings.append(f"合并重复缺陷“{d.title}”（{d.path}:{d.line}）")
            continue
        seen.add(key)
        bad = [e for e in d.evidence_ids if e not in known]
        if bad:
            warnings.append(f"缺陷“{d.title}”引用了不存在的证据 {bad}，已去掉")
        name, sev, kc = DEFECT_TYPES[d.type]
        isc, ibu = df.change_flags(diff, d.path, d.line)
        out.append(ReportDefect(**{**d.model_dump(), "evidence_ids": [e for e in d.evidence_ids if e in known]},
                                severity=sev, type_name=name, knowledge_category=kc,
                                in_student_change=isc, in_baseline_unchanged=ibu))
    return out, warnings
