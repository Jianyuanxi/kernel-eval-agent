# agent（块 5）

Dify 智能体的全部“源码”：

| 目录 | 内容 |
|---|---|
| `prompts/` | 指令（system.md）和后端发给智能体的消息模板。占位符 `{xxx}` 由后端填，名字不能改 |
| `knowledge/` | 操作系统知识库的 Markdown 原文（自己写的总结），导入 Dify 知识库 `os-knowledge` |
| `dsl/` | 从 Dify 导出的应用 DSL `kernel-eval-agent.yml` |

详细任务说明见 `docs/tasks/块5-智能体与知识库.md`。踩坑见 `NOTES.md`。

## 从零重建（约 15 分钟）

前提：能登录 <http://132.232.242.186:8080/>；模型供应商已由组长配好（`deepseek/deepseek-flash`、`kinfra-text-embedding-0.6b`）。

### 1. 自定义工具

1. 集成 → 工具 → **Swagger API 作为工具** → 创建。
2. 名称：`kernel_eval_tools`。
3. Schema：粘贴仓库 `contracts/tools.openapi.yaml` 全文（`servers.url` 保持公网 `http://132.232.242.186`）。
4. 鉴权：请求头 → Custom；键 `X-Tool-Token`；值：`ssh kernel-eval` 后 `grep ^KE_TOOL_TOKEN= /opt/kernel-eval/kernel-eval.env`。
5. 保存后应看到 6 个工具。可用已有 `task_id` 测 `list_files`。

### 2. 知识库

1. 知识库 → 创建即用型 → 名称 `os-knowledge`。
2. 上传 `agent/knowledge/` 下全部 Markdown（10 份：K_* 与 MiniEuler）。
3. 分段：自定义，分隔符 `\n## `，最大长度 800。
4. 索引：高质量；向量模型 `kinfra-text-embedding-0.6b`。
5. 检索：混合检索，语义 0.7 / 关键词 0.3，Top K 4，不开重排。
6. **不要**在知识库里写往届样例的具体缺陷位置或“标准答案”，只写通用原理与 MiniEuler 一般写法。

若索引报 `PGVECTOR_PASSWORD`：确认 `/opt/dify/docker/envs/vectorstores/pgvector.env` 存在且含 `PGVECTOR_HOST=pgvector` 等，并重启 Dify 的 api/worker。

### 3. Agent 应用

1. 工作室 → 创建应用 → **Agent**（不是 Chatflow），名称 `kernel-eval-agent`。
2. 模型：`deepseek/deepseek-flash`；Agent 策略：**函数调用**；最大迭代 **20**。
3. 指令：粘贴 `agent/prompts/system.md`（**必须去掉**开头 `<!-- … -->` 注释，不要带进 Dify）。
4. 工具：添加 `kernel_eval_tools` 的 6 个工具（配置里 `provider_id` 必须是工具 UUID）。
5. 上下文：添加知识库 `os-knowledge`。
6. 关掉开场白与建议问题 → 发布。
7. 访问 API → 创建密钥（`app-…`），**私聊发给块 1** 写入 `KE_DIFY_APP_KEY`；不要进仓库。

也可导入本目录 `dsl/kernel-eval-agent.yml` 再检查工具鉴权与知识库绑定。

### 4. 阶段 1 关卡（需块 1 配合）

服务器：`KE_MOCK_MODULES=ingest,buildrun,analyze,diff,scoring`，已填 `KE_DIFY_APP_KEY`。上传样例 1 zip → start → 轮询到 done，报告里应有 agent 的 compile/run/clang/read_source、knowledge，且能点出 `src/shell/shmsg.c` 约第 96 行越界。
