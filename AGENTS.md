# AGENTS.md：给 AI 的开发规则

本仓库是操作系统课程项目“内核代码评测智能体”，6 人分 6 块开发，每人用自己的 AI。完整规范在 `docs/`，这里是必须遵守的精简版。

## 开工先读

1. `docs/tasks/块N-*.md`：你负责的那一块要做什么、接口、测试、验收标准（**最重要**）
2. `docs/02-接口规范.md`：编号、目录、函数签名、接口、已验证的编译运行扫描规则
3. `docs/04-开发规范.md`：目录归属、分支、提交、测试
4. 需要时再读：`docs/01-总体设计.md`、`docs/03-评分规则.md`、`docs/05-服务器与环境.md`、`docs/06-验收标准.md`

## 硬规则

- **只推自己的分支**（`blockN-…`），不推 main、不 `--force`；main 只通过 PR 合并（见下文“工作流程”）。
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

## 工作流程（你自己执行，不用等用户提醒）

用户通常只说一句“开始”或“继续”。下面每一步都由你自己判断和执行，能用命令或浏览器完成的不要让用户手工做。

任务说明最后的“阶段”按顺序做。阶段不绑定日期：用户时间多可以一次连着做完几个阶段，但**每个阶段做完都要单独提交、推送、提 PR**，不要攒成一个大 PR。

### 0. 先摸清进度、预估时间、问用户

每次新对话开始时：

1. 看现在做到哪了：`git log --oneline -10`、`git status`、`gh pr list --author @me --state all`（没有 gh 就看分支和 NOTES.md），对照任务说明的阶段表和验收标准，判断哪个阶段做完了、哪个做到一半。
2. 预估接下来要多久：当前阶段还要多久、做完全部剩余阶段大概多久。按你实际干活的时间算，**单独列出需要用户配合的环节**（登录、在浏览器里点确认、等别人的模块）。
3. 预计超过 30 分钟时，先把预估告诉用户，问他这次有多少时间、想做到哪个阶段，等回答再动手。时间紧就先做当前阶段的必做项，选做项放后面，不砍测试。
4. 用户说了时间后按计划做；中途发现明显超出预估，停下来说明原因和新的预估。

### 1. 开工前同步

`git fetch origin`。在 main 上就 `git pull --ff-only`；在自己分支上就 `git merge origin/main`。不用 rebase，免得要强推。有冲突先告诉用户冲突在哪，不要擅自取舍别人的代码。

### 2. 建分支

不在 main 上改。没有分支就从最新的 main 建 `blockN-简短英文`（例如 `block2-ingest`）。之后的阶段可以继续用这个分支（上一个 PR 合并后先 `git merge origin/main`），也可以新开一个。

### 3. 小步提交

每做完一个能跑通测试的小功能就 commit。Conventional Commits，类型英文、描述中文：`feat: 实现 zip 解压与工程识别`。`git add` 前看 `git status`，只加自己块目录里的文件，不用 `git add -A`。

### 4. 及时推送，只推自己的分支

- 每次 commit 后、每次结束工作前都推：`git push -u origin blockN-xxx`。
- **只推自己的分支**：不推 main，不推别人的分支，不用 `--force`。main 只能通过 PR 合并。
- 推之前跑一遍测试，再看 `git diff origin/main --stat` 和 diff 内容：没有密钥（`sk-`、`app-`、`BEGIN OPENSSH`）、没有样例代码、没有往届学生姓名学号、没有改到别人块的目录。
- 第一次推送时如果弹出 GitHub 登录窗口，让用户在窗口里登录一次，以后就不用了。

### 5. 阶段做完就提 PR

测试全过、已经推送后，提 PR 合进 main：

1. 检查 `gh`：`gh --version`。没装就告诉用户要装 GitHub CLI，同意后 `winget install --id GitHub.cli -e`（macOS 用 `brew install gh`），装完可能要重开终端。`gh auth status` 显示没登录就运行 `gh auth login --web --git-protocol https`，把屏幕上的一次性验证码告诉用户，让他在弹出的浏览器页里输入并授权。这一步只做一次。
2. 同一个分支已经有没合并的 PR（`gh pr view` 能看到）就不要再建，推送会自动更新它，在 PR 里补一条评论说明新增了什么即可。
3. 没有就新建：把描述写进一个临时文件（不放仓库里），然后
   ```bash
   gh pr create --base main --head blockN-xxx --title "块N 阶段M：一句话说明" --body-file <临时文件>
   ```
   描述按这个格式：
   ```markdown
   ## 完成的阶段
   块 N 阶段 M（对应任务说明第 X 节）
   ## 做了什么
   - ……
   ## 怎么测的
   命令和结果（贴 pytest 最后一行；服务器上跑的写明在服务器跑）
   ## 还没做 / 需要别人配合
   - ……
   ```
4. 等 CI：`gh pr checks --watch`。红了用 `gh run view --log-failed` 看原因，修好后提交、推送同一分支，直到变绿。
5. 把 PR 链接告诉用户，请他转给块 1 审核。块 1 提了修改意见（`gh pr view --comments`）就照着改，推同一分支。
6. 实在装不了 `gh`：用浏览器打开 `https://github.com/Jianyuanxi/kernel-eval-agent/compare/main...blockN-xxx?expand=1`。你能控制浏览器就自己填标题和描述、点 “Create pull request”；不能就把链接、标题、描述一起给用户，让他粘进去点一下。

### 6. PR 合并后

`gh pr view <号> --json state` 显示 MERGED 后：`git checkout main && git pull --ff-only`，再回到自己分支 `git merge origin/main`，或者开新分支，继续下一个阶段。

### 7. 记踩坑

遇到的问题和解决办法随手写进自己块的 `NOTES.md`（块 2 `backend/app/ingest/NOTES.md`，块 3 `backend/app/buildrun/NOTES.md`，块 4 `backend/app/analyze/NOTES.md`，块 5 `agent/NOTES.md`，块 6 `frontend/NOTES.md`，块 1 `deploy/NOTES.md`），和代码一起提交。最后的 Word 指导书从这里汇总。

### 8. 每次结束时给用户一段进度

3～5 行：完成了什么、PR 链接和状态（CI 绿没绿、合并没有）、卡在哪、下一步做什么。用户直接转发到群里，所以写成别人看得懂的话。

### 停下来问用户的情况

接口或 schemas 不够用、需要改别人块的目录、要加新依赖、测试在本机跑不了、冻结签名看起来有问题、要装软件、要用户登录或授权。不要自己绕过去。

## 浏览器

你的工具能控制浏览器时（例如 Codex 的浏览器、Claude 的浏览器插件、Cursor 的浏览器），下面这些直接在浏览器里做，不用让用户手工点：

- GitHub：接受仓库邀请页、看 PR 和 CI 结果、在没有 `gh` 时创建 PR。
- Dify 后台 <http://132.232.242.186:8080/>（块 5、块 1）：建工具、知识库、应用，调提示词，看日志，导出 DSL。
- 部署好的网页 <http://132.232.242.186/>（块 6、块 1）：走一遍上传到追问的流程、截图。
- 查资料：Dify、Vue、clang、QEMU 的官方文档。

边界：登录、输入密码由用户自己来；不点删除、不改仓库和 Dify 的系统设置、不合并 PR（块 1 审核时除外）；Dify 里的模型和 API Key 组长已经配好，不要动。
