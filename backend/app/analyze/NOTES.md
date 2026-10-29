# 块 4 静态分析踩坑记录

- Windows 端虽然有 Docker 命令，但 Docker Desktop 的 Linux 引擎未启动；需要沙箱的验收在服务器 `~/dev/kuaisi/` 执行，且设置 `KE_REQUIRE_SANDBOX=1`。
- 本机系统 Python 是 3.14；使用 Codex 附带的 Python 3.12 创建虚拟环境。该运行时的 `venv` 初始化 pip 失败，改用本机 pip 的 `--python backend/.venv` 给 3.12 环境安装项目固定依赖。
- Windows 沙箱的默认临时目录不可写，pytest 需要指定工作区内的 `--basetemp`；整仓测试另需设置可写的 `KE_DATA_ROOT`。
- clang 的 `compile_commands.json` 记录容器路径 `/workspace/...`，不能直接把原始上传目录传进沙箱。预处理参数中的相对 `-I`、`-include` 路径需要按编译命令的 `directory` 归一化。
- 配置失败或没有编译数据库时，保留 `full` 模式，但改用片段参数；片段缺头文件时如实返回 `unsupported`。
- 服务器实测：样例 1 扫描 14/15 个 C 文件、7 条告警；样例 3 为 unsupported、覆盖率 0；样例 4 扫描 19/19 个 C 文件、7 条告警、覆盖率 1.0。

- 10 个补丁均在服务器上独立应用并编译通过；A01/A02/A03 的新增告警已分别验证为 NULL_DEREF、DIV_ZERO、UNINIT_VAR。样例 1 使用 CRLF，补丁上下文必须保留回车，否则 Linux 服务器上的 git apply 无法应用。
- 2026-10-27 服务器公开后端的健康检查仍显示 analyze、scoring 为假模块；在它们切到真实模式前，run_eval.py 会拒绝生成检出率，避免把假报告当作验收结果。
- 2026-10-29 服务已全部真实运行，但阶段 3 的首份基线任务因 AGENT_TIMEOUT（420 秒）失败，未生成基线报告；任务编号和复现步骤记录于 evaluation/进度.md。不能把任务失败当作零检出率，也不能跳过基线直接统计。
