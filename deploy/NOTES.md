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
- 2026-10-28 切 scoring（块 6 阶段 1–3，PR #10，部署 9c2c5fc）：`KE_MOCK_MODULES=`（空值，全部真实），改前备份 `kernel-eval.env.bak-20261028`。合并前服务器全量测试 253 passed、`npm ci && npm run build` 成功。样例 1 全真实跑到 done：67 分（及格），可靠性 0/25（20 条缺陷，18 条计分；vsnprintf_s.c、prt_sem.c 两条标为参考代码原有，不计分）。网页：上传页、进度时间线、报告页各节都正常；追问约 30 秒内返回，记成 source=followup，分数不变；导出 JSON/Markdown 都是 200。
- 2026-10-29 解决智能体超时（PR #13）：查 Dify 的 `message_agent_thoughts` 表，超时那次 19 轮，输入从 2.7 千涨到 13.3 万 tokens（读过的源码每轮都重发），每轮推理输出 5～8 千 tokens，最终报告 1.8 万 tokens；吞吐稳定在 160～190 tokens/秒，不是限流。改成评审时 read_source 最多成功 20 次（`KE_READ_SOURCE_MAX`，超过返回 READ_LIMIT）、智能体预算 600 秒、S4 放宽到 10 分钟。改后样例 1：8 轮、输入 37.6 万 / 输出 2.6 万 tokens（改前 93～118 万 / 5.7～8.2 万），智能体 156 秒，整次 3 分 11 秒，仍是 67 分，5 条主要缺陷不变。
- 2026-11-01 最终一键验收（main e25c20a，含块 5 阶段 3 提示词）：10/11 pass。5 个样例/工程全部 done，单次 190～372 秒；S5 没过：样例 1 两次 73 / 81 分，差 8 分（要求 ≤5），差在可靠性（第一次计了 2 条严重缺陷 4 分，第二次 0 条严重 14 分），是模型每次找到的缺陷不同。
- 2026-11-01 提速与稳定（分支 block1-agent-speed）：评审前按规则预读关键源码（有告警的 → 新增 → 修改的 C 文件和说明文档，最多 4000 行）附在第一条消息里；clang 报过的位置缺陷类型按映射表定；漏调知识库被提醒时保留第一次的缺陷和功能判断；Dify `max_iteration` 20→5（库里 `app_model_configs.agent_mode` 同步改，原值 20）；内核启动了但没进 shell 时重跑一次（样例 1 偶发 EXC_STORM，编译运行分 19→9）；修了并行轮里工具名用 `;` 拼接、认不出知识库导致每次多发提醒的 bug。样例 1 连跑 3 次：69 / 70 / 67 分（改前差 8～10），122～290 秒。跑满轮数时 DeepSeek 在最后一轮仍会用 DSML 文本写工具调用、不出 JSON，触发一次格式修正（约 65 秒）。
- 正式服务以 `ubuntu` 用户运行、在 docker 组里；块 3 加固后的沙箱拒绝 root 运行，以后不要把服务改成 root。

## 踩坑

1. **TokenHub 免费额度会用完**：每个模型单独领免费额度，用完后调用返回 402「免费体验额度已耗尽」，Dify 对话直接失败。要在腾讯云控制台 TokenHub → 启用管理 → 对应模型打开「按 Token 计费」（从账户余额扣，余额不足会报欠费）。deepseek-flash 已于 2026-10-22 开通，对应 DeepSeek-V4.1-Flash-1017，闲时输入 1 元、输出 4 元每百万 tokens，高峰翻倍。
2. **推理模型的思考段**：deepseek-flash 的回答开头带 `<think>…</think>`。`dify_client.chat()` 返回前统一去掉，评测 JSON 解析和追问展示都拿到干净答案。
3. **追问很吃 token**：同一会话带着整次评测的上下文，一次追问约 11.6 万输入 tokens（约 0.1～0.2 元）。演示时不用担心，批量测试时注意。
4. **Dify 报的价格是 0**：OpenAI-API-compatible 插件没填单价，message_end 里的 price 全是 0，实际花费去 TokenHub「用量统计」看。
5. **余额扣光会被隔离**：2026-10-29 16:05 起所有评测 AGENT_ERROR，Dify 里是 402 / `403004`「API Key 所属账号已欠费，访问的服务 ID 已被隔离」。充值后要回控制台确认服务恢复，再重跑。一次 `run_samples.py --repeat 2` 约 700 万输入 tokens（8～17 元），批量跑前先看余额。
6. **glm-5.3-flash 免费额度只够约 3 次评测**：2026-11-01 试过把应用切到 glm-5.3-flash 省钱：能跑通（样例 1 69 分），但单次评测约 600 秒，碰到时间预算；约 100 万 tokens 后免费额度用完，返回 402 / `401008`。已切回 deepseek-flash。查用量：`docker exec docker-db_postgres-1 psql -U postgres -d dify -c "select model_id, count(*), sum(message_tokens) from messages group by 1"`。
