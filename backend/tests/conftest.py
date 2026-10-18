"""测试统一用临时数据目录。配置在 import app 时读取，所以必须在这里先设好环境变量。

- 默认 KE_MOCK_MODULES=all：只测编排和接口。各块测自己的真实模块时，在测试文件里直接 import 模块函数，不走 mock。
- 想在本机用真实模块跑冒烟：KE_MOCK_MODULES=agent pytest tests/test_smoke.py（需要沙箱镜像，只在服务器上能跑）
- 需要 Docker 和沙箱镜像的测试加 @pytest.mark.sandbox：没有 docker 命令、守护进程没起、没有镜像时自动跳过；
  服务器验收时设 KE_REQUIRE_SANDBOX=1，沙箱不可用直接报错，不允许跳过后算通过。
"""
import os
import shutil
import subprocess
import tempfile

import pytest

os.environ.setdefault("KE_DATA_ROOT", tempfile.mkdtemp(prefix="ke-test-"))
os.environ.setdefault("KE_MOCK_MODULES", "all")
os.environ.setdefault("KE_TOOL_TOKEN", "test-token")

from app import config  # noqa: E402  必须在设好环境变量之后


def _sandbox_problem() -> str:
    """沙箱不可用的原因；可用时返回空串"""
    if shutil.which("docker") is None:
        return "没有 docker 命令"
    try:
        r = subprocess.run(["docker", "image", "inspect", config.SANDBOX_IMAGE], capture_output=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"docker 无响应：{e}"
    if r.returncode != 0:
        return f"docker 守护进程没起，或没有镜像 {config.SANDBOX_IMAGE}"
    return ""


def pytest_configure(config):
    config.addinivalue_line("markers", "sandbox: 需要 Docker 和沙箱镜像，不可用时跳过（KE_REQUIRE_SANDBOX=1 时报错）")


def pytest_collection_modifyitems(config, items):
    marked = [i for i in items if "sandbox" in i.keywords]
    if not marked:
        return
    why = _sandbox_problem()
    if not why:
        return
    if os.getenv("KE_REQUIRE_SANDBOX") == "1":
        raise pytest.UsageError(f"KE_REQUIRE_SANDBOX=1，但沙箱不可用：{why}")
    for i in marked:
        i.add_marker(pytest.mark.skip(reason=f"需要沙箱：{why}"))
