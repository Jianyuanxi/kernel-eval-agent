# 系统验收结果

| 编号 | 项目 | 结果 | 依据 |
| --- | --- | --- | --- |
| S1 | 样例走通 | pass | 1 t202610291355459b4c1e done 176.2s；4 t202610291358427192ef done 178.2s；2-lab10 t20261029140140f6ea9e done 186.2s；2-lab6_pro t20261029140447cdc120 done 294.3s；3 t20261029140942b4cbd1 done 212.2s |
| S2 | 多工程识别 | pass | 任务 t20261029141314c85d6a，11 个工程：['lab1', 'lab10', 'lab2', 'lab2_hw1', 'lab4', 'lab5', 'lab5_pro', 'lab6', 'lab6_pro', 'lab8', 'lab9'] |
| S3 | 片段模式 | pass | 任务 t20261029140942b4cbd1 mode=fragment build=None run=None scan.coverage=0.0 计分满分之和=80.0 总分=59 |
| S4 | 耗时 | pass | 1 t202610291355459b4c1e 176.2s；4 t202610291358427192ef 178.2s；2-lab10 t20261029140140f6ea9e 186.2s；2-lab6_pro t20261029140447cdc120 294.3s；3 t20261029140942b4cbd1 212.2s |
| S5 | 稳定 | pass | 未重复（--repeat 1），第一次总分 67 |
| S6 | 位置真实 | pass | 检查 184 处，全部合法 |
| S7 | 工具调用 | pass | 1 read_source=True knowledge=True agent=28；4 read_source=True knowledge=True agent=29；2-lab10 read_source=True knowledge=True agent=28；2-lab6_pro read_source=True knowledge=True agent=28；3 read_source=True knowledge=True agent=28 |
| S8 | 检出率 | fail | 块 4 的 evaluation/result.md 还不在仓库或服务器上，本项引用它 |
| S9 | 容错 | pass | txt → UPLOAD_BAD_TYPE；坏 zip → UPLOAD_BAD_ZIP；编译不过 t2026102914131501e4fc done build=failed 226.3s；死循环 t2026102914170197ec81 done 188.2s |
| S10 | 追问 | pass | 任务 t202610291355459b4c1e 5.5s 回答 482 字，分数 67→67 |
| S11 | 导出 | pass | 任务 t202610291355459b4c1e json=200 md=200 含总分 67 |

合计：10/11 pass
