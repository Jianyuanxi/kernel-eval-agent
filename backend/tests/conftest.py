"""测试统一用临时数据目录。配置在 import app 时读取，所以必须在这里先设好环境变量。

- 默认 KE_MOCK_MODULES=all：只测编排和接口。各块测自己的真实模块时，在测试文件里直接 import 模块函数，不走 mock。
- 想在本机用真实模块跑冒烟：KE_MOCK_MODULES=agent pytest tests/test_smoke.py（需要沙箱镜像，只在服务器上能跑）
"""
import os
import tempfile

os.environ.setdefault("KE_DATA_ROOT", tempfile.mkdtemp(prefix="ke-test-"))
os.environ.setdefault("KE_MOCK_MODULES", "all")
os.environ.setdefault("KE_TOOL_TOKEN", "test-token")
