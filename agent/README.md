# agent（块 5）

Dify 智能体的全部“源码”：

| 目录 | 内容 |
|---|---|
| `prompts/` | 指令（system.md）和后端发给智能体的消息模板。占位符 `{xxx}` 由后端填，名字不能改 |
| `knowledge/` | 操作系统知识库的 Markdown 原文（自己写的总结），导入 Dify 知识库 `os-knowledge` |
| `dsl/` | 从 Dify 导出的应用 DSL `kernel-eval-agent.yml` |

怎么在 Dify 里搭建见 `docs/tasks/块5-智能体与知识库.md` 第 4 节。块 5 完成后在这里补上“从零重建”的步骤和模型对比结果。
