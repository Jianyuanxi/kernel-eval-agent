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
- 知识库：`os-knowledge`（阶段 1 先导入 K_ADDR、K_CRIT、MiniEuler 三份）
- 应用：`kernel-eval-agent`（deepseek/deepseek-flash，Function Calling，max 20）
