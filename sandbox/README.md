# 沙箱镜像

编译、运行、clang 扫描都在这个镜像的一次性容器里做（断网、非 root、限 CPU/内存/进程数），调用方式见 `backend/app/buildrun/sandbox.py`。

**服务器上已经建好 `kernel-eval-sandbox:0.1`，一般不用重建。** 只有改了 Dockerfile 才需要重建，由块 3 负责，改完在群里说一声。

## 重建

```bash
cd sandbox
# 工具链包约 150MB，服务器 ~/spike/sandbox/ 里有一份，直接复制，不用重新下载
cp ~/spike/sandbox/aarch64-none-elf.tar.xz .
# 官方下载地址（服务器上下得很慢）：
# https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf.tar.xz
docker build -t kernel-eval-sandbox:0.1 .
```

## 手动试跑

```bash
# 编译（work 目录是拷过来并改好工具链路径的工程）
docker run --rm --network none --user $(id -u):$(id -g) -v $PWD/work:/workspace kernel-eval-sandbox:0.1 \
  sh -c 'cmake -S src -B build && cmake --build build'
# 运行 20 秒
docker run --rm -i --network none -v $PWD/work:/workspace kernel-eval-sandbox:0.1 \
  timeout 20 qemu-system-aarch64 -machine virt,gic-version=2 -m 1024M -cpu cortex-a53 -nographic -nic none \
  -serial mon:stdio -kernel build/miniEuler
```

已验证的规则（工具链改写、产物名、GIC 版本、QEMU 参数）见 `docs/02-接口规范.md` 第 7 节。
