"""所有配置都从环境变量读，前缀 KE_。本地开发把 deploy/env.example 复制成 backend/.env 再改。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")  # 已经设置的环境变量优先（服务器用 systemd 的 EnvironmentFile）


def _env(name: str, default: str) -> str:
    return os.getenv(f"KE_{name}", default)


DATA_ROOT = Path(_env("DATA_ROOT", str(BACKEND_DIR / "data"))).resolve()
TASKS_ROOT = DATA_ROOT / "tasks"
# 参考代码（创新点 C），固定 commit，见 docs/02 第 6 节
REF_ROOT = Path(_env("REF_ROOT", str(DATA_ROOT / "ref" / "os2024_exp_redo_kp"))).resolve()
REF_COMMIT = "0bd1ef59f32867842f0c3047a58d62bced82d54b"
# 测试样例：不进仓库，各人放在 kernel-eval-agent/samples/ 或服务器 /data/kernel-eval/samples/
SAMPLES_ROOT = Path(_env("SAMPLES_ROOT", str(REPO_DIR / "samples"))).resolve()
EXAMPLES_DIR = REPO_DIR / "contracts" / "examples"

SANDBOX_IMAGE = _env("SANDBOX_IMAGE", "kernel-eval-sandbox:0.1")
BUILD_TIMEOUT_S = int(_env("BUILD_TIMEOUT_S", "180"))
RUN_WINDOW_S = int(_env("RUN_WINDOW_S", "20"))
SCAN_TIMEOUT_S = int(_env("SCAN_TIMEOUT_S", "300"))

UPLOAD_MAX_BYTES = 20 * 1024 * 1024
UNPACK_MAX_BYTES = 100 * 1024 * 1024
UNPACK_MAX_FILES = 5000

# Dify 调工具时带的令牌（请求头 X-Tool-Token）
TOOL_TOKEN = _env("TOOL_TOKEN", "dev-token")
DIFY_API_BASE = _env("DIFY_API_BASE", "http://127.0.0.1:8080/v1")
DIFY_APP_KEY = _env("DIFY_APP_KEY", "")
AGENT_TIMEOUT_S = int(_env("AGENT_TIMEOUT_S", "420"))
# 只用于写进报告；真正用哪个模型在 Dify 应用里选，两边要一致
MODEL_NAME = _env("MODEL_NAME", "deepseek/deepseek-flash")

# 用假数据顶替还没做好的模块，逗号分隔：ingest,buildrun,analyze,diff,agent,scoring；all 表示全部
_mock = _env("MOCK_MODULES", "")
MOCK_MODULES = {"ingest", "buildrun", "analyze", "diff", "agent", "scoring"} if _mock.strip() == "all" else {
    m.strip() for m in _mock.split(",") if m.strip()}


def is_mock(module: str) -> bool:
    return module in MOCK_MODULES
