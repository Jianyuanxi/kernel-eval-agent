# deploy NOTES（块 1）

## 阶段 1 关卡（2026-10-22 通过）

- 配置：`KE_MOCK_MODULES=ingest,buildrun,analyze,diff,scoring`，`KE_DIFY_APP_KEY` 已填（块 5 交的 `app-` 密钥）。
- 样例 1 任务 `t20261022114152710052` 走到 done，总分 79。工具记录里 source=agent 的有 list_files、compile_project、run_kernel、clang_scan、diff_reference、read_source（36 次）和 knowledge（2 次）。第一条缺陷是 `src/shell/shmsg.c:96 OUT_OF_BOUNDS`，warnings 为空。
- Dify 客户端：报告里 agent_thought、工具名、knowledge 都解析正确，说明 `core/dify_client.py` 的事件字段和 Dify 1.17.1 一致。
- 追问：用报告里的 conversation_id 和 `user=task-<任务号>` 直接调 `http://127.0.0.1:8080/v1/chat-messages`（streaming）再问一句，能接着上下文答出 shmsg.c:96，message_end 的 conversation_id 不变。

## 切真实模块记录

- 2026-10-24 切 ingest（块 2 阶段 1，PR #3，部署 d270701）：`KE_MOCK_MODULES=buildrun,analyze,diff,scoring`，改前 env 备份为 `kernel-eval.env.bak-20261024`。四份样例上传：样例 1 为 1 个工程（50 文件/15 个 C），样例 2 为 11 个工程，样例 3 为 1 个片段（riscv64，不可编译），样例 4 为 1 个工程（61/19），全部 aarch64 完整工程可编译。样例 1 完整跑到 done，79 分，warnings 空，agent 调了全部 6 个工具和 knowledge。diff 等块 2 阶段 2 再切。
- 2026-10-25 切 diff（块 2 阶段 2，PR #4）和 buildrun（块 3，PR #5），部署 23a4018：`KE_MOCK_MODULES=analyze,scoring`，改前备份 `kernel-eval.env.bak-20261025`。合并前把两个 PR 合在一起，在服务器用真实沙箱、四份样例、参考代码跑全量后端测试（`KE_REQUIRE_SANDBOX=1`）：202 passed，0 skipped。生产验收：样例 1 编译通过（2 警告、0 错误，产物 `build/miniEuler`），运行出提示符并完成 top/tick 交互（约 20 秒），对比基线 lab10、相同 14 / 修改 26 / 新增 10，和契约示例一致；完整跑到 done，79 分，warnings 空。lab6_pro 两种表现（正常完成 / EXC_STORM）见块 3 的 NOTES，生产上未单独跑。
- 2026-10-27 切 analyze（块 4 阶段 1、2，PR #8、#9，部署 fb2843b）：`KE_MOCK_MODULES=scoring`，改前备份 `kernel-eval.env.bak-20261027`。合并前服务器全量测试 239 passed，0 skipped。样例 1 生产跑到 done：clang 扫描 full 模式 14/15 个文件、7 条告警、约 8 秒，日志在 `logs/p1/scan.log`；编译、运行、对比结果和上次一致，79 分（scoring 仍为 mock）。
- 正式服务以 `ubuntu` 用户运行、在 docker 组里；块 3 加固后的沙箱拒绝 root 运行，以后不要把服务改成 root。

## 踩坑

1. **TokenHub 免费额度会用完**：每个模型单独领免费额度，用完后调用返回 402「免费体验额度已耗尽」，Dify 对话直接失败。要在腾讯云控制台 TokenHub → 启用管理 → 对应模型打开「按 Token 计费」（从账户余额扣，余额不足会报欠费）。deepseek-flash 已于 2026-10-22 开通，对应 DeepSeek-V4.1-Flash-1017，闲时输入 1 元、输出 4 元每百万 tokens，高峰翻倍。
2. **推理模型的思考段**：deepseek-flash 的回答开头带 `<think>…</think>`。`dify_client.chat()` 返回前统一去掉，评测 JSON 解析和追问展示都拿到干净答案。
3. **追问很吃 token**：同一会话带着整次评测的上下文，一次追问约 11.6 万输入 tokens（约 0.1～0.2 元）。演示时不用担心，批量测试时注意。
4. **Dify 报的价格是 0**：OpenAI-API-compatible 插件没填单价，message_end 里的 price 全是 0，实际花费去 TokenHub「用量统计」看。
