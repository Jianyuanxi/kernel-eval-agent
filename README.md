# kernel-eval-agent

操作系统课程项目：**内核代码评测智能体**。上传一份 MiniEuler 内核代码，系统在沙箱里编译、在 QEMU 里运行、用 clang 静态分析、和参考实验代码对比，再由智能体（Dify + 国产大模型）调用这些工具、读源码、查操作系统知识库，输出带分项评分、缺陷清单、知识点讲解和修改建议的评测报告，可导出、可追问。

- 网站：<http://132.232.242.186/>
- 接口文档：<http://132.232.242.186/docs>

## 文档

| 文件 | 内容 |
|---|---|
| [docs/01-总体设计.md](docs/01-总体设计.md) | 架构、技术栈、流程、功能、创新点、时间安排 |
| [docs/02-接口规范.md](docs/02-接口规范.md) | 编号、目录、函数签名、网页接口、工具接口、已验证规则 |
| [docs/03-评分规则.md](docs/03-评分规则.md) | 四项评分怎么算 |
| [docs/04-开发规范.md](docs/04-开发规范.md) | 目录归属、分支、提交、测试 |
| [docs/05-服务器与环境.md](docs/05-服务器与环境.md) | 服务器、SSH、部署、Dify、本地开发 |
| [docs/06-验收标准.md](docs/06-验收标准.md) | 系统验收 S1–S12 |
| [docs/tasks/](docs/tasks/) | 六块各自的任务说明 |
| [AGENTS.md](AGENTS.md) | 给 AI 的开发规则 |

## 快速开始

```bash
git clone git@github.com:Jianyuanxi/kernel-eval-agent.git
cd kernel-eval-agent/backend
pip install -r requirements.txt
python -m pytest -q
cp ../deploy/env.example .env        # 删掉前 3 行服务器路径；默认 KE_MOCK_MODULES=all，全部用假数据
python -m uvicorn app.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000/docs> 试接口。

## 目录

```text
backend/     后端（FastAPI）：core 编排、ingest 工程处理、buildrun 编译运行、analyze 静态分析、scoring 评分、followup 追问
frontend/    网页（Vue 3 + Vite）
agent/       Dify 智能体：提示词、知识库、导出的 DSL
contracts/   工具接口 OpenAPI、示例 JSON
sandbox/     沙箱镜像（交叉编译器 + QEMU + clang）
evaluation/  植入缺陷测试（创新点 A）
acceptance/  一键验收脚本
deploy/      部署脚本、nginx、systemd
docs/        规范与任务说明
```
