"""读取 agent/prompts/ 下的提问模板（块 5 维护内容，块 1 只负责填变量）。

模板里用 {变量名} 占位，只替换传入的变量，其余花括号（比如 JSON 示例）原样保留。
"""
from app.config import REPO_DIR

PROMPTS_DIR = REPO_DIR / "agent" / "prompts"


def render(name: str, **values) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    # 模板开头可以有一段 <!-- 给人看的说明 -->，发给模型前去掉
    if text.lstrip().startswith("<!--"):
        text = text.split("-->", 1)[1]
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text.strip()
