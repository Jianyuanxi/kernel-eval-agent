# agent NOTES（块 5）

## 环境

- 服务器同步拼音：`tangyingqi` → `~/dev/tangyingqi/`
- 本机代理：`127.0.0.1:7897`（gh/git 访问 GitHub）
- 工具令牌、`app-` 密钥只进 Dify / 服务器 env，不进仓库

## 阶段 1 踩坑

1. **自定义工具鉴权**：请求头 Custom，键 `X-Tool-Token`，值取自服务器 `KE_TOOL_TOKEN`。
2. **Agent 工具 `provider_id`**：必须填自定义工具的 **UUID**（如 `13dedd27-…`），不能填名字 `kernel_eval_tools`，否则会报 `invalid input syntax for type uuid`，对话 500。
3. **知识库向量库**：服务器原先缺 `/opt/dify/docker/envs/vectorstores/pgvector.env`，高质量索引会因 `PGVECTOR_PASSWORD` 失败。已补上并重启 `api/worker/worker_beat`（与 compose 默认密码一致）。
4. **Agent Chat API**：只支持 `response_mode=streaming`，不支持 blocking。
5. **阶段 1 关卡样例**：`t20261022114152710052`，发现 `src/shell/shmsg.c:96` `OUT_OF_BOUNDS`；agent 调了 compile/run/clang/read_source，有 knowledge/dataset 检索；warnings 空。
6. **TokenHub 额度**：关卡跑完后同一会话追问曾报 402「免费体验额度已耗尽」，需组长在 TokenHub 控制台开后付费后再验 followup。

## Dify 资源名

- 工具：`kernel_eval_tools`
- 知识库：`os-knowledge`（10 份 knowledge 文档；勿写样例具体缺陷答案）
- 应用：`kernel-eval-agent`（deepseek/deepseek-flash，Function Calling，max 20）
- 粘贴「指令」时去掉 `system.md` 开头 HTML 注释

## 阶段 2

- 知识库已去样例剧透（K_ADDR / MiniEuler），并补全 K_MEM/SYNC/IRQ/CTX/SYSCALL/DEV/GENERAL（共 10 份）
- 提示词加强片段模式：compile/run/clang 失败勿编造、勿死磕；无 R 证据时功能点慎标 done
- 多样例复核（全真实模式）：样例1 `t2026102915235927c023` 仍检出 shmsg.c:96 OUT_OF_BOUNDS；样例4 / 2-lab10 / 2-lab6_pro / 样例3 均 done，工具与 knowledge 齐全，warnings 空
- 模型对比（选做）未做，继续用 deepseek/deepseek-flash
