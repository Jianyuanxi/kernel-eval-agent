<!-- 块 5 维护。后端每次评测发给智能体的第一条消息。可用占位符：{task_id} {project_id} {project_name} {mode} {arch} {c_files} {required_tools} -->
请评审这个内核工程。

- task_id：{task_id}
- project_id：{project_id}
- 工程名：{project_name}
- 类型：{mode}（架构 {arch}，{c_files} 个 C 文件）
- 本次必须调用的工具：{required_tools}

按指令里的评审步骤做，所有工具都带上面的 task_id 和 project_id。最后只输出一个符合格式的 JSON 代码块。
