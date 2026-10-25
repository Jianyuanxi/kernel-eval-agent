# 编译与运行开发记录

## 阶段一 编译

编译只操作工作副本，原始工程保持不变。课程工程中写死的工具链目录通过公共 `prepare_workspace` 改成 `/opt/toolchain`。构建启用 `compile_commands.json`，供静态分析模块使用。

学生代码编译失败与工具不可用需要区分：编译失败返回 `failed`；Docker 不可用抛出 `SandboxError`，由公共流水线转换成工具错误。链接器的 RWX 警告不计入工程内警告数。诊断最多保留一百条，但警告和错误总数不受证据数量上限影响。

本地运行 Python 3.12 和不需要 Docker 的单元测试；真实编译与运行在独立 Ubuntu 24.04 x86 服务器中验收。开发机下载依赖后传到测试机，可以解决测试机不能访问海外软件仓库的问题。登录凭据保存在仓库外，不随代码同步。

阶段一验收：本地全量测试 `121 passed, 3 skipped`（三项真实编译测试需要 Docker）；服务器设置 `KE_REQUIRE_SANDBOX=1` 后，本块测试 `17 passed`。两份完整样例均编译成功；损坏源码的测试返回 `src/main.c` 错误位置。

服务器不能直连 Docker Hub 时，从 Canonical 官方 OCI 目录下载 Ubuntu 24.04 amd64 根文件系统，核对官方 SHA256 清单后传到服务器，用 `docker import` 导入为 `ubuntu:24.04`。仓库 Dockerfile 保持不变，通过 `--build-arg APT_MIRROR=http://repo.huaweicloud.com/ubuntu` 选择可访问的软件源。交叉工具链仍使用 Arm 官方 13.3.Rel1 的 x86_64 主机版本。
