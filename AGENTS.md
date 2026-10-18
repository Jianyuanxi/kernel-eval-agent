# AGENTS.md：给 AI 的开发规则

本仓库是操作系统课程项目“内核代码评测智能体”，6 人分 6 块开发，每人用自己的 AI。完整规范在 `docs/`，这里是必须遵守的精简版。

## 开工先读

1. `docs/tasks/块N-*.md`：你负责的那一块要做什么、接口、测试、验收标准（**最重要**）
2. `docs/02-接口规范.md`：编号、目录、函数签名、接口、已验证的编译运行扫描规则
3. `docs/04-开发规范.md`：目录归属、分支、提交、测试
4. 需要时再读：`docs/01-总体设计.md`、`docs/03-评分规则.md`、`docs/05-服务器与环境.md`、`docs/06-验收标准.md`

## 硬规则

- **只改自己块的目录**（docs/04 第 1 节的表）。`backend/app/schemas/`、`contracts/`、`backend/app/core/`、`backend/requirements.txt` 归块 1。
- **冻结的函数签名不能改**（各模块 `__init__.py` 里写了“签名已冻结”）。可以在模块目录里新建文件拆分实现。
- 不准为了让测试通过而改 schemas、`contracts/examples/`、别人的测试，不准删测试、降断言、加 skip。
- 数据结构以 `backend/app/schemas/` 为准，示例以 `contracts/examples/*.json` 为准；输出必须能被对应 pydantic 模型校验。
- 结果里的路径一律相对工程根、用 `/`；行号从 1 开始。
- 读学生代码：`encoding="utf-8", errors="replace"`。调外部命令：`subprocess.run([...])` 列表形式、带超时，不用 `shell=True`。
- 调 docker 一律通过 `app.buildrun.sandbox.run_in_sandbox`，不要自己拼 docker 命令。
- Python 3.12，类型注解，模块和函数写一句中文 docstring；不加没人要的抽象和配置项。前端 Vue 3 + Vite + JavaScript。
- 新依赖不能自己加进 requirements.txt，先告诉用户在群里提。

## 不能进仓库

- 测试样例（`samples/`）、植入缺陷补丁（`evaluation/patches/`）：含往届学生代码
- 任何密钥：服务器私钥、TokenHub Key（`sk-`）、Dify 应用密钥（`app-`）、工具令牌、`.env`
- **往届学生的姓名、学号**不能出现在代码、注释、文档、测试里，样例一律叫“样例 1–4”

`git add` 前看一眼 `git status`，只加自己改的文件。

## 测试

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
```

- 自己的测试放 `backend/tests/<模块名>/`。
- 需要 Docker 的测试加 `@pytest.mark.sandbox`：`tests/conftest.py` 会检查 docker 命令、守护进程和沙箱镜像，缺一个就跳过（CI、Windows 上自动跳过）。在服务器上跑时加 `KE_REQUIRE_SANDBOX=1`，沙箱不可用直接报错，不允许“跳过了就算通过”。
- 需要样例的测试：从 `app.config.SAMPLES_ROOT` 找，找不到 `pytest.skip`。
- **改完要真的跑测试，看到通过再说做完了**；跑不了（比如本机没 Docker）就明说哪些没跑。

本地联调：不建 `.env` 时默认全部假数据。要换成自己的真实模块，把 `deploy/env.example` 复制成 `backend/.env`，**删掉开头 3 行服务器路径**，用 `KE_MOCK_MODULES` 让别人还没做好的模块用假数据（例如块 2 用 `KE_MOCK_MODULES=buildrun,analyze,agent,scoring`），然后 `cd backend && python -m uvicorn app.main:app --reload --port 8000`，打开 <http://127.0.0.1:8000/docs>。

## 服务器

需要 Docker / 沙箱镜像时用组里的服务器（`ssh kernel-eval`，配置见 docs/05）：

- 只在 `~/dev/<自己拼音名>/` 下干活：`bash deploy/devsync.sh <拼音名>` 把本地代码同步过去
- 不要动 `/opt/kernel-eval/`、`/opt/dify/`；`/data/kernel-eval/` 只读（块 4 的 `evaluation/` 子目录除外）；不要重启 docker、不要 `apt upgrade`
- 服务器连不上 GitHub，代码靠 devsync / deploy 脚本从本地推过去

## 提交与分支

- 分支 `blockN-简短英文`，PR 合进 main，CI（pytest）必须绿
- Conventional Commits，类型英文、描述中文：`feat: 实现 zip 解压与工程识别`
- PR 描述写做了什么、怎么测的（命令和结果）

## 踩坑记录

在自己块的目录维护 `NOTES.md`（块 5 是 `agent/NOTES.md`，块 6 是 `frontend/NOTES.md`，块 1 是 `deploy/NOTES.md`），遇到问题和解决办法随手记。
