# 块 2 工程处理记录

## 阶段 1（2026-10-22）

- Windows 本地开发使用 Python 3.12。上传整理、文件清单和读源码只用标准库，未增加依赖。
- zip 文件名未设置 UTF-8 标志时，先逆转 cp437，再尝试 UTF-8 和 GBK；测试通过修改 zip 文件名原始字节覆盖两种情况。
- 路径检查同时考虑 POSIX 和 Windows：拒绝绝对路径、上级目录、反斜杠、盘符、设备名、备用数据流，以及重复和大小写冲突。目录和文件重名也拒绝，避免平台行为不同。
- 安全检查先于过滤；被过滤条目也必须接受路径、加密和链接检查，并计入解压字节数与文件数上限。读取过程中按块累计，不能只信压缩包声明大小。
- 先在任务内临时目录整理，验证通过才发布 unpacked/ 和 projects/。输入失败不会留下可供后续模块使用的半成品；已有结果拒绝覆盖。
- 源码行数以 LF 为准，CRLF 先归一化。不使用 splitlines()，因为它还会把垂直制表符和孤立 CR 当作换行；末尾 LF 不额外产生空行。
- 工程识别先选父目录再检查子目录，避免 src/ 被重复识别。完整工程以外的文件计入 ignored_count。
- 本地四份样例全部直接参与测试，并经 FastAPI TestClient 上传、查询任务验证工程列表；测试代码只保存验收数字，不含样例源码或个人信息。CI 缺少样例时按仓库规则跳过对应测试。
- 阶段 1 的 API 验证只启用真实 ingest；diff 等模块保持 mock，阶段 2 再验证真实差异分析。
- 基础环境已有 Starlette 关于 httpx TestClient 的弃用警告；未改动块 1 管理的依赖。

## 待配合

- 阶段 1 PR 需块 1 审核合并；不由块 2 合并。
- 服务器真实模式上传验收尚未进行，需要块 1 完成集成后协同验证。

## 阶段 2（2026-10-24）

- 实现参考 lab 路径交集匹配，按实验编号数值处理并列；lab10 优先于 lab8，不依赖目录枚举顺序。
- 比较前移除 CR、行尾空白和末尾空行；保留行首空白和中间空行。使用 SequenceMatcher 的 autojunk=False，学生侧 insert/replace 形成闭区间，参考侧 delete/replace 计入 removed_lines。
- 只删除内容时 hunks 为空；新增空文件仍是 added，但 added_lines=0、hunks=[]，避免违反 LineRange 的正行号约束。
- 按文本比较要求，学生侧或参考侧含 NUL 的文件不进入 files，note 报告跳过数；这些文件仍参与同路径基线统计，change_flags 对它们返回未知，不能误判为基线未变。
- 只给 added/modified 按路径排序分配 D1、D2 等证据；same 的编号为空。change_flags 直接使用闭区间，不把文件的未修改行算作修改行。
- 样例 1 完整输出与 contracts/examples/diff_result.json 逐字段相等：lab10，相同 14、修改 26、新增 10；src/main.c 第 56–57 行均被标为学生改动。
- 样例 4：lab10，相同 49、修改 9、新增 3。样例 3：unsupported，无异常。
- 真实 ingest/diff 的四份样例通过上传、启动评测、报告和工具接口验证；其余模块保持 mock，不代表编译、模型或服务器已验收。
- 公共 tests/conftest.py 会把 DATA_ROOT 指向临时目录，连带改变默认 REF_ROOT。要运行本地参考样例测试，必须显式设 KE_REF_ROOT；否则会按缺少参考代码跳过。PowerShell 在仓库根目录运行：

  ```powershell
  $env:KE_REF_ROOT = (Resolve-Path backend/data/ref/os2024_exp_redo_kp).Path
  backend/.venv/Scripts/python -m pytest -q backend/tests
  ```

- 本地结果：140 passed, 1 warning in 29.34s；所有样例测试均运行，无 skip。

### 集成交接

请块 1 合并阶段 2 后部署，并将 KE_MOCK_MODULES 中的 ingest、diff 同时移除（其他模块按各自完成度决定），确保 KE_REF_ROOT 指向已准备好的参考代码。随后上传四份样例确认工程数为 1/11/1/1，样例 1、4 的差异数字如上。块 2 不修改 /opt/kernel-eval 的代码、配置或服务；服务器验收尚待配合。

### Linux 开发目录验证

- 开发目录：~/dev/Liu/。2026-10-24 通过 SSH 在组内服务器运行全量测试：140 passed, 1 warning in 4.72s，无 skip。
- 使用 /opt/kernel-eval/venv/bin/python，KE_REF_ROOT=/data/kernel-eval/ref/os2024_exp_redo_kp、KE_SAMPLES_ROOT=/data/kernel-eval/samples；运行数据及临时文件均放 ~/dev/Liu/ 内。
- 四份样例的真实 ingest/diff API 流水线测试均通过。这里使用 FastAPI TestClient，不是生产网站端到端验收；编译、扫描、智能体和评分保持 mock。
- 生产健康检查显示 mock_modules 包含 analyze、buildrun、diff、scoring，ingest 已为真实模块；diff 的部署切换仍由块 1 处理。
- Windows 私钥 ACL 中出现一条额外 SID 权限时，OpenSSH 会拒绝私钥。仅移除该额外权限后连接成功，没有输出密钥内容。
- deploy/devsync.sh 会删除整个目标开发目录；本次确认 ~/dev/Liu 尚不存在后，使用 git archive 打包已提交代码并传入该目录解压，未调用脚本的递归删除步骤，未上传样例、密钥或本地运行数据。

## 阶段 3（2026-10-26）

- 补充测试先复现 4 个失败用例，再修复两类问题：父目录仅大小写不同会被 Windows 静默合并；read_source 的 resolve 阶段权限错误或链接循环没有转换成 PathInvalidError。
- 上传时检查每一级路径的大小写拼写一致性；源码读取把解析和读文件放在同一个错误转换边界内。未更改冻结签名、公共契约或其他模块。
- 生产健康接口已确认 ingest、diff、buildrun 为真实模块，mock_modules 只有 analyze、scoring。
- 通过服务器已部署的 HTTP 上传和任务查询接口验证四份样例，工程数为 1/11/1/1，架构符合要求，样例 1 为 50 文件/15 C，样例 4 为 61 文件/19 C。任务均停在 waiting_select，没有触发模型评测。
- 验收任务编号（仅作为服务侧证据，不含样例源码）：样例 1 t20261026113220dfbdbf；样例 2 t20261026113220b574c9；样例 3 t202610261132208ea383；样例 4 t20261026113220e73fef。
- Linux 验证目录 ~/dev/Liu/stage3-20261026/：`python -B -m pytest -q -m "not sandbox"` 得到 182 passed, 24 deselected, 1 warning in 5.23s。显式配置服务器样例和参考目录，24 个未执行项是块 3 的 Docker 测试；本次不重复运行内核编译和 QEMU。
- Windows 全量结果为 8 failed, 174 passed, 24 skipped；8 个失败全部来自新合并的块 3 测试：3 个符号链接权限错误、2 个 os.getuid 不存在、3 个默认 GBK 解码错误。相同非 Docker 测试在 Linux 全部通过，未改别人的测试或系统权限来掩盖问题，请块 3 后续处理 Windows 兼容性。
- 阶段 1、2 已合并，服务器真实模式上传关卡已通过。本次路径边界修补仍需块 1 审核部署。
