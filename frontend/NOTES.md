# 块 6 踩坑记录

## 评分

- Python 的 `round(78.5)` 在银行家舍入下会变成 78。百分制必须用 `int(raw / max_sum * 100 + 0.5)`，与 docs/03 和 `score_result.json` 的 78.5→79 一致。
- `compute_score` 会就地改 `defects[i].counted`。测试里每次调用前要 `model_copy`，否则第二次结果被第一次污染。
- 样例 1 功能点原因的顿号/逗号必须用中文逗号：`完成 7 项，部分完成 1 项（任务调度）`，功能点名称取 `FEATURE_NAMES`。

## 前端骨架

- 任务号放进 hash 路由 `/#/task/{id}`，刷新后 `GET /api/tasks/{id}` 按 stage 恢复到选工程 / 进度 / 报告占位。
- `vite.config.js` 把 `/api` 代理到 `http://127.0.0.1:8000`，请求不要写死 IP。
- 进度页用 `GET /api/tasks/{id}/events?after=已有最大 seq`，2 秒一次，只追加新记录。
- 本机 Node 是 v26，任务说明写的是 22。Vite 7 能构建即可；服务器用 `npm ci`，以提交的 lock 为准。
- 阶段 1 未引入 Element Plus / ECharts，报告页占位只显示总分，避免半截依赖。阶段 2 再加雷达图和导出。

## 本地联调

后端假数据：`cd backend && python -m uvicorn app.main:app --reload --port 8000`（不建 `.env` 时默认 `KE_MOCK_MODULES=all`）。
前端：`cd frontend && npm install && npm run dev`。上传任意 zip 会走到样例 1 的假报告。
