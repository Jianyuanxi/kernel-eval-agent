# 块 6 踩坑记录

## 评分

- Python 的 `round(78.5)` 在银行家舍入下会变成 78。百分制必须用 `int(raw / max_sum * 100 + 0.5)`，与 docs/03 和 `score_result.json` 的 78.5→79 一致。
- `compute_score` 会就地改 `defects[i].counted`。测试里每次调用前要 `model_copy`，否则第二次结果被第一次污染。
- 样例 1 功能点原因的顿号/逗号必须用中文逗号：`完成 7 项，部分完成 1 项（任务调度）`，功能点名称取 `FEATURE_NAMES`。

## 报告导出

- `render_markdown` 放在 `scoring/markdown.py`，`__init__.py` 只保留冻结签名。`score is None` 的项写成「不计分」。
- 示例报告的构建日志很长，Markdown 不塞 `log_tail`，网页里用折叠块展示。

## 前端骨架

- 任务号放进 hash 路由 `/#/task/{id}`，刷新后 `GET /api/tasks/{id}` 按 stage 恢复到选工程 / 进度 / 报告占位。
- `vite.config.js` 把 `/api` 代理到 `http://127.0.0.1:8000`，请求不要写死 IP。
- 进度页用 `GET /api/tasks/{id}/events?after=已有最大 seq`，2 秒一次，只追加新记录。
- 本机 Node 是 v26，任务说明写的是 22。Vite 7 能构建即可；服务器用 `npm ci`，以提交的 lock 为准。
- 雷达图用 ECharts，只画 `score !== null` 的项，数值是得分率（得分/满分 × 100）。
- 源码抽屉走 `GET /api/tasks/{id}/source`，窗口 200 行。假数据模式下文件必须真的在上传包里，报告里的路径才打得开。
- 追问必须带评测时的 `user=task-{id}` 和 `conversation_id`，否则 Dify 会新开会话。知识库工具名以 `dataset_` 开头，要补记 `source=followup, tool=knowledge`。
- 切换 `/#/task/{id}` 时要在 `watch(id)` 里重新 `loadTask`/`getReport`，不能只清空 `report`，否则会一直停在「正在加载报告…」。
- 一键验收脚本在假数据下会因为样例 2 识别不出 11 个工程而失败，这是预期；最终 `acceptance/result.md` 要在服务器真实模式跑完再提交。

## 阶段 4 打磨

- 报告页增加 sticky 目录导航，对应 docs/06 S12 各块，长页可锚点跳转。**不要用 `href="#id"`**，Vue Router 的 hash 模式会把锚点当成路由；用按钮 + `scrollIntoView`。
- 报告加载中与追问等待用 `.spinner` 提示；warnings 区块用 `warn-card` 样式并放在追问之前。
- S12 截图命名与说明见 `acceptance/screenshots/README.md`；指导书章节在 `frontend/指导书.md`。

## 本地联调

- 审查修复：追问 Markdown 使用独立的 `Marked` 渲染器，原始 HTML 转义，链接仅允许 http/https/mailto，图片仅允许 http/https，避免 `v-html` 执行回答里的标签或脚本协议；不新增依赖。
- 轮询改成请求结束后再等待 2 秒，单工程自动开始只启动一次；页面每次重新加载或离开时更新版本号，旧请求返回后不再写入当前任务。
- 已完成任务加载报告失败会自动重试，错误提示提供「重新加载」按钮；成功后清除错误并停止轮询。
- 追问发送前固定缺陷索引和标题，等待期间切换缺陷不会改变已发问题的归属。
- `cd frontend && npm test`：用 Node 自带测试工具及 Vue 编译器检查真实组件脚本，模拟接口、计时器及乱序响应；覆盖上述边界情况。

后端假数据：`cd backend && python -m uvicorn app.main:app --reload --port 8000`（不建 `.env` 时默认 `KE_MOCK_MODULES=all`）。
前端：`cd frontend && npm install && npm run dev`。上传任意 zip 会走到样例 1 的假报告。
