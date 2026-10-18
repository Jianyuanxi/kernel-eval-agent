<!-- 块 6 使用、块 5 调优。用户在报告页追问时发给智能体的消息，接在评测时的同一个会话后面。占位符：{task_id} {project_id} {question} {defect} -->
评审已经完成。用户对报告有一个追问，请直接用中文回答，不要再输出 JSON。

- task_id：{task_id}
- project_id：{project_id}
- 用户问的是这条缺陷（没有指定则为空）：{defect}

问题：{question}

需要看代码时调用 read_source，需要讲知识点时检索知识库。回答 300 字以内，可以带少量代码。
