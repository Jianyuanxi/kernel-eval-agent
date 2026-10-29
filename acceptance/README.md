# acceptance（块 6）

一键验收脚本 `run_samples.py`：在服务器真实模式下跑 `docs/06-验收标准.md` 的 S1–S11，输出 `result.md`。要求见 `docs/tasks/块6-网页评分与追问.md` 第 5 节。

```bash
python acceptance/run_samples.py --base http://132.232.242.186 --samples /data/kernel-eval/samples --out acceptance/result.md --repeat 2
```

S8 读取块 4 的 `evaluation/result.md`，文件不存在时记 fail。S12 是手工截图，不在脚本里。

跑完后把 `result.md` 提交进仓库。若 S8 尚未就绪或样例 1 在公网评测超时，可先合并阶段 4，再在服务器上重跑脚本更新该文件。

