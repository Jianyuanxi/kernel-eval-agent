# 编译与运行开发记录

## 阶段一 编译

编译只操作工作副本，原始工程保持不变。课程工程中写死的工具链目录通过公共 `prepare_workspace` 改成 `/opt/toolchain`。构建启用 `compile_commands.json`，供静态分析模块使用。

学生代码编译失败与工具不可用需要区分：编译失败返回 `failed`；Docker 不可用抛出 `SandboxError`，由公共流水线转换成工具错误。链接器的 RWX 警告不计入工程内警告数。诊断最多保留一百条，但警告和错误总数不受证据数量上限影响。

本地运行 Python 3.12 和不需要 Docker 的单元测试；真实编译与运行在独立 Ubuntu 24.04 x86 服务器中验收。开发机下载依赖后传到测试机，可以解决测试机不能访问海外软件仓库的问题。登录凭据保存在仓库外，不随代码同步。

阶段一验收：本地全量测试 `121 passed, 3 skipped`（三项真实编译测试需要 Docker）；服务器设置 `KE_REQUIRE_SANDBOX=1` 后，本块测试 `17 passed`。两份完整样例均编译成功；损坏源码的测试返回 `src/main.c` 错误位置。

服务器不能直连 Docker Hub 时，从 Canonical 官方 OCI 目录下载 Ubuntu 24.04 amd64 根文件系统，核对官方 SHA256 清单后传到服务器，用 `docker import` 导入为 `ubuntu:24.04`。仓库 Dockerfile 保持不变，通过 `--build-arg APT_MIRROR=http://repo.huaweicloud.com/ubuntu` 选择可访问的软件源。交叉工具链仍使用 Arm 官方 13.3.Rel1 的 x86_64 主机版本。

## 阶段二 运行与真实样例差异

样例一在 `src/shell/shmsg.c` 中逐字符比较 `cmd[0]`、`cmd[1]` 等，而不是使用任务说明列出的 `strcmp`。增加对连续下标字符比较的提取，保留字符串比较和命令表规则，最终识别 `top`、`tick`、`mem`。同时支持 `src/kernel/shell/` 下的命令实现。

QEMU 自己的状态行不能算启动输出或混入命令证据。只有带已发送命令回显的行才确认 shell 提示符。样例二 lab10 没有运行脚本，必须从源文件注释读取 GIC 3。

当前分发的 lab6_pro 表现不稳定：前两次在 GIC 2 下运行二十秒，得到 4163 字节输出，两个任务均完成，没有 `Catch a exception.`。前 2105 字节是启动横幅及换行，其余为初始化、配置、任务执行和 QEMU 结束消息。后续全量测试中同一原始工程触发异常刷屏，保留的 262144 字节日志中包含 12938 条 `Catch a exception.`，模块正确返回 `failed`、`EXC_STORM` 和 `OUTPUT_TRUNCATED`。

因此不能把前两次正常运行当作固定预期，也不能仅按文件夹名称强制判失败。集成测试严格按实际串口证据分别检查任务完成和刷屏两种结果；独立自写故障内核确保每次都实际验证异常分支。触发条件尚未定位，不把时序或版本差异当作已证实原因。原样例没有被改写。

用于比对版本的 SHA256 摘要：

| 文件 | SHA256 |
| --- | --- |
| lab6_pro 的 `src/main.c` | `021f2097cecdd33bcfec153960d8c6e1aa45cc57e93e6803647ff879ebd9df11` |
| lab6_pro 的 `src/CMakeLists.txt` | `b7c5733ba01a17feb662217d2ef9f122911031596f9ba4e424c1094c3c7e8474` |

独立自写的刷屏内核严格验证 `failed`、`EXC_STORM`、`OUTPUT_TRUNCATED`、256KB 日志上限和三十秒结束。独立静默死循环内核验证两种 GIC 均尝试、`NO_OUTPUT` 和六十秒结束。这样故障测试不依赖某份往届作业是否恰好触发异常。
