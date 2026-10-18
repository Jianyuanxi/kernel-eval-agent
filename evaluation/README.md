# evaluation（块 4，创新点 A）

植入缺陷测试：在样例 1、样例 4 上人为植入 10 个已知缺陷，统计只用 clang 和完整系统各检出几个。要求见 `docs/tasks/块4-静态分析与缺陷测试.md` 第 5 节。

| 文件 | 进仓库 |
|---|---|
| `truth.yaml`：每个植入缺陷的位置、类型、预期 | 是 |
| `run_eval.py`：统计脚本 | 是 |
| `result.md`：统计结果表 | 是 |
| `patches/*.patch`：补丁（含样例代码） | **否**，放服务器 `/data/kernel-eval/evaluation/patches/` |
