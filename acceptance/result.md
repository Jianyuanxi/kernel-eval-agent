# 系统验收结果

| 编号 | 项目 | 结果 | 依据 |
| --- | --- | --- | --- |
| S1 | 样例走通 | pass | 1 t20261102231000684817 done 158.2s；4 t202611022312389e5f25 done 192.2s；2-lab10 t20261102231551f059ce done 216.2s；2-lab6_pro t20261102231928f6d593 done 188.2s；3 t2026110223223693ac2a done 206.2s |
| S2 | 多工程识别 | pass | 任务 t20261102232603c0de8d，11 个工程：['lab1', 'lab10', 'lab2', 'lab2_hw1', 'lab4', 'lab5', 'lab5_pro', 'lab6', 'lab6_pro', 'lab8', 'lab9'] |
| S3 | 片段模式 | pass | 任务 t2026110223223693ac2a mode=fragment build=None run=None scan.coverage=0.0 计分满分之和=80.0 总分=69 |
| S4 | 耗时 | pass | 1 t20261102231000684817 158.2s；4 t202611022312389e5f25 192.2s；2-lab10 t20261102231551f059ce 216.2s；2-lab6_pro t20261102231928f6d593 188.2s；3 t2026110223223693ac2a 206.2s |
| S5 | 稳定 | pass | t20261102231000684817=69，t20261102232603ed375a=64，差 5，第二次 266.3s |
| S6 | 位置真实 | pass | 检查 145 处，全部合法 |
| S7 | 工具调用 | pass | 1 read_source=True knowledge=True agent=10；4 read_source=True knowledge=True agent=14；2-lab10 read_source=True knowledge=True agent=18；2-lab6_pro read_source=True knowledge=True agent=10；3 read_source=True knowledge=True agent=15 |
| S8 | 检出率 | pass | 引用 evaluation/result.md：系统检出 7，clang 检出 3 |
| S9 | 容错 | pass | txt → UPLOAD_BAD_TYPE；坏 zip → UPLOAD_BAD_ZIP；编译不过 t2026110223303061ffc4 done build=failed 112.1s；死循环 t202611022332221bed2c done 182.2s |
| S10 | 追问 | pass | 任务 t20261102231000684817 4.2s 回答 563 字，分数 69→69 |
| S11 | 导出 | pass | 任务 t20261102231000684817 json=200 md=200 含总分 69 |

合计：11/11 pass
