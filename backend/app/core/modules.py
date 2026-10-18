"""按 KE_MOCK_MODULES 选用真实模块或假数据模块。编排代码只通过这里拿模块。"""
import importlib

from app import config
from app.core import mocks

_REAL = {
    "ingest": "app.ingest", "diff": "app.ingest", "buildrun": "app.buildrun",
    "analyze": "app.analyze", "scoring": "app.scoring", "followup": "app.followup",
}


def get(name: str):
    if config.is_mock(name) or (name == "followup" and config.is_mock("agent")):
        return getattr(mocks, name)
    return importlib.import_module(_REAL[name])
