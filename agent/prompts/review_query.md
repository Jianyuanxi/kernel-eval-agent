<!-- 块 5 维护（2026-11-01 块 1 为提速改过流程）。后端每次评测发给智能体的第一条消息。可用占位符：{task_id} {project_id} {project_name} {mode} {arch} {c_files} {required_tools} {first_tools} {preloaded} -->
请评审这个内核工程。

- task_id：{task_id}
- project_id：{project_id}
- 工程名：{project_name}
- 类型：{mode}（架构 {arch}，{c_files} 个 C 文件）
- 本次必须调用的工具：{required_tools}

编译、运行、clang 扫描、参考代码对比都已经跑完。下面附上了后端按规则挑出的关键源码（工具告警所在的文件、学生新增和修改的 C 文件、说明文档），编号 S1、S2……，可以直接在 evidence_ids 里引用。

为了快，按下面三步做，尽量少来回：

1. 第一轮**一次性同时**调用：{first_tools}。知识库按本工程涉及的知识点检索（例如信号量、中断、任务切换、内存越界）。不要分几轮调。
2. 结合工具结果和下面的源码判断功能点、找缺陷。附上的源码不用再读；附件之外确实要看的文件或行，再用 read_source 补读（至少调用一次，用来确认最关键的那条缺陷；需要读多段时在同一轮并行调用）。补读最多 3 轮，之后就输出 JSON（第 6 轮工具会被收回，那时再写工具调用就成了无效回答）。
3. 然后直接输出最终 JSON。

缺陷类型：clang 告警确认是真问题时，type 用 clang_scan 结果里该告警的 defect_type；自己发现的问题优先用具体类型，实在归不了类才用 OTHER_*。

所有工具都带上面的 task_id 和 project_id。最后只输出一个符合格式的 JSON 代码块。

## 已附源码

{preloaded}
