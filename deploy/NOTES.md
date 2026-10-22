# deploy NOTES（块 1）

## 阶段 1 关卡（2026-10-22 通过）

- 配置：`KE_MOCK_MODULES=ingest,buildrun,analyze,diff,scoring`，`KE_DIFY_APP_KEY` 已填（块 5 交的 `app-` 密钥）。
- 样例 1 任务 `t20261022114152710052` 走到 done，总分 79。工具记录里 source=agent 的有 list_files、compile_project、run_kernel、clang_scan、diff_reference、read_source（36 次）和 knowledge（2 次）。第一条缺陷是 `src/shell/shmsg.c:96 OUT_OF_BOUNDS`，warnings 为空。
- Dify 客户端：报告里 agent_thought、工具名、knowledge 都解析正确，说明 `core/dify_client.py` 的事件字段和 Dify 1.17.1 一致。
- 追问：用报告里的 conversation_id 和 `user=task-<任务号>` 直接调 `http://127.0.0.1:8080/v1/chat-messages`（streaming）再问一句，能接着上下文答出 shmsg.c:96，message_end 的 conversation_id 不变。

## 踩坑

1. **TokenHub 免费额度会用完**：每个模型单独领免费额度，用完后调用返回 402「免费体验额度已耗尽」，Dify 对话直接失败。要在腾讯云控制台 TokenHub → 启用管理 → 对应模型打开「按 Token 计费」（从账户余额扣，余额不足会报欠费）。deepseek-flash 已于 2026-10-22 开通，对应 DeepSeek-V4.1-Flash-1017，闲时输入 1 元、输出 4 元每百万 tokens，高峰翻倍。
2. **推理模型的思考段**：deepseek-flash 的回答开头带 `<think>…</think>`。`dify_client.chat()` 返回前统一去掉，评测 JSON 解析和追问展示都拿到干净答案。
3. **追问很吃 token**：同一会话带着整次评测的上下文，一次追问约 11.6 万输入 tokens（约 0.1～0.2 元）。演示时不用担心，批量测试时注意。
4. **Dify 报的价格是 0**：OpenAI-API-compatible 插件没填单价，message_end 里的 price 全是 0，实际花费去 TokenHub「用量统计」看。
