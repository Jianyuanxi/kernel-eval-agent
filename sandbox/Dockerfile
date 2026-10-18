# 编译、运行、扫描用的沙箱镜像：aarch64-none-elf 交叉工具链 + CMake + QEMU + clang
# 构建方法见 sandbox/README.md。镜像名固定 kernel-eval-sandbox:0.1（backend 配置 KE_SANDBOX_IMAGE）
FROM ubuntu:24.04

ARG APT_MIRROR=http://mirrors.tencentyun.com/ubuntu
RUN sed -i "s#http://archive.ubuntu.com/ubuntu#${APT_MIRROR}#g; s#http://security.ubuntu.com/ubuntu#${APT_MIRROR}#g" /etc/apt/sources.list.d/ubuntu.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends cmake make qemu-system-arm clang clang-tools python3 xz-utils ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# 工具链包需事先放到本目录并改名为 aarch64-none-elf.tar.xz（ADD 会自动解压）
ADD aarch64-none-elf.tar.xz /opt/
# /opt/toolchain 是统一路径：编译工具会把学生 CMakeLists 里各式各样的工具链路径改写成它
# /root/aarch64-none-elf 保留给想手动跑样例脚本的人；容器以宿主普通用户 uid 运行（--user），/root 要放开遍历权限
RUN ln -s /opt/arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf /opt/toolchain \
 && ln -s /opt/arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf /root/aarch64-none-elf \
 && chmod 755 /root \
 && /opt/toolchain/bin/aarch64-none-elf-gcc --version | head -1

ENV HOME=/tmp
WORKDIR /workspace
