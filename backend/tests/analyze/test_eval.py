"""植入缺陷统计只接纳新增且位置与类型都匹配的报告条目。"""
import importlib.util

from app import config

spec = importlib.util.spec_from_file_location("run_eval", config.REPO_DIR / "evaluation/run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


def test_score_filters_baseline_and_requires_exact_type():
    """原有告警和泛化类型不能算植入缺陷检出。"""
    truth = {"path": "src/main.c", "line": 20, "type": "RACE", "accept_types": ["IRQ_NOT_RESTORED"]}
    baseline = {
        "scan": {"findings": [{"path": "src/main.c", "line": 20, "defect_type": "RACE", "message": "old"}]},
        "defects": [{"path": "src/main.c", "line": 20, "type": "RACE", "title": "old"}],
    }
    report = {
        "scan": {"findings": [
            {"path": "src/main.c", "line": 20, "defect_type": "RACE", "message": "old"},
            {"path": "src/main.c", "line": 21, "defect_type": "OTHER_SEVERE", "message": "new"},
        ]},
        "defects": [
            {"path": "src/main.c", "line": 20, "type": "RACE", "title": "old"},
            {"path": "src/main.c", "line": 21, "type": "IRQ_NOT_RESTORED", "title": "new"},
        ],
    }
    assert run_eval._score(truth, report, baseline) == (False, True, "new")
    report["scan"]["findings"].append(
        {"path": "src/main.c", "line": 23, "defect_type": "RACE", "message": "new"}
    )
    assert run_eval._score(truth, report, baseline) == (True, True, "new")


def test_markdown_contains_rates_and_escapes_title():
    """统计行只包含编号、类型、命中情况与标题。"""
    table = run_eval._markdown([
        ("A01", "NULL_DEREF", True, True, "空指针|崩溃"),
        ("A02", "DIV_ZERO", False, True, "除零"),
    ])
    assert "1/2（50%）" in table and "2/2（100%）" in table
    assert "空指针\\|崩溃" in table


def test_reworded_baseline_is_excluded_but_nearby_new_location_counts():
    """同位置原有问题换标题不算新增，邻近植入位置的新问题仍可计入。"""
    truth = {"path": "shell.c", "line": 46, "type": "OUT_OF_BOUNDS"}
    baseline = {"scan": {"findings": []}, "defects": [
        {"path": "shell.c", "line": 43, "type": "OUT_OF_BOUNDS", "title": "原有写越界"},
    ]}
    report = {"scan": {"findings": []}, "defects": [
        {"path": "shell.c", "line": 43, "type": "OUT_OF_BOUNDS", "title": "换了一种说法"},
    ]}
    assert run_eval._score(truth, report, baseline) == (False, False, "")
    report["defects"].append(
        {"path": "shell.c", "line": 46, "type": "OUT_OF_BOUNDS", "title": "新增读越界"}
    )
    assert run_eval._score(truth, report, baseline) == (False, True, "新增读越界")
