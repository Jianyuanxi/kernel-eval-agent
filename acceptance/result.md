# 系统验收结果

| 编号 | 项目 | 结果 | 依据 |
| --- | --- | --- | --- |
| S1 | 样例走通 | pass | 1 t20261101155947fa6072 done 274.3s；4 t20261101160422756eae done 190.2s；2-lab10 t20261101160732ce2a2f done 206.2s；2-lab6_pro t202611011610592f5c97 done 304.4s；3 t20261101161604cd1747 done 372.4s |
| S2 | 多工程识别 | pass | 任务 t2026110116221692415f，11 个工程：['lab1', 'lab10', 'lab2', 'lab2_hw1', 'lab4', 'lab5', 'lab5_pro', 'lab6', 'lab6_pro', 'lab8', 'lab9'] |
| S3 | 片段模式 | pass | 任务 t20261101161604cd1747 mode=fragment build=None run=None scan.coverage=0.0 计分满分之和=80.0 总分=53 |
| S4 | 耗时 | pass | 1 t20261101155947fa6072 274.3s；4 t20261101160422756eae 190.2s；2-lab10 t20261101160732ce2a2f 206.2s；2-lab6_pro t202611011610592f5c97 304.4s；3 t20261101161604cd1747 372.4s |
| S5 | 稳定 | fail | t20261101155947fa6072=73，t2026110116221766ef7b=81，差 8，第二次 320.4s |
| S6 | 位置真实 | pass | 检查 177 处，全部合法 |
| S7 | 工具调用 | pass | 1 read_source=True knowledge=True agent=28；4 read_source=True knowledge=True agent=27；2-lab10 read_source=True knowledge=True agent=28；2-lab6_pro read_source=True knowledge=True agent=27；3 read_source=True knowledge=True agent=26 |
| S8 | 检出率 | pass | 引用 evaluation/result.md：系统检出 7，clang 检出 3 |
| S9 | 容错 | pass | txt → UPLOAD_BAD_TYPE；坏 zip → UPLOAD_BAD_ZIP；编译不过 t20261101162738b3269d done build=failed 222.2s；死循环 t202611011631206f5961 done 196.2s |
| S10 | 追问 | pass | 任务 t20261101155947fa6072 5.0s 回答 374 字，分数 73→73 |
| S11 | 导出 | pass | 任务 t20261101155947fa6072 json=200 md=200 含总分 73 |

合计：10/11 pass
