"""Dify chat-messages 流式客户端（旧式 Agent 应用）。

按 Dify 1.17.1 的事件定义写成：agent_thought（按 id 合并）、agent_message/message（答案分片）、
message_end（拿 conversation_id）、error。块 1 在阶段 1 关卡用真实应用联调确认，接口不变。
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from app.config import AGENT_TIMEOUT_S, DIFY_API_BASE, DIFY_APP_KEY
from app.schemas import AgentThought

# DeepSeek 等推理模型会把思考过程以 <think>…</think> 放在答案开头，评测解析和追问展示都不要它
_THINK = re.compile(r"<think>.*?</think>\s*", re.S)


def strip_think(answer: str) -> str:
    """去掉答案里的 <think>…</think> 思考段。"""
    return _THINK.sub("", answer)


class DifyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # AGENT_ERROR / AGENT_TIMEOUT


@dataclass
class ChatResult:
    answer: str
    conversation_id: str
    message_id: str = ""
    thoughts: list[AgentThought] = field(default_factory=list)


class DifyClient:
    def __init__(self, api_base: str = DIFY_API_BASE, app_key: str = DIFY_APP_KEY, timeout_s: int = AGENT_TIMEOUT_S):
        self.api_base = api_base.rstrip("/")
        self.app_key = app_key
        self.timeout_s = timeout_s

    def chat(self, query: str, user: str, conversation_id: str = "",
             on_thought: Callable[[AgentThought], None] | None = None, deadline: float | None = None) -> ChatResult:
        """发一条消息并等完整回答。user 固定用 f"task-{task_id}"，追问时必须和第一次相同。

        deadline：time.monotonic() 的截止时刻，几次调用共用一个预算时传同一个值；不传就是从现在起 timeout_s 秒。
        到点不管是否还在收数据都抛 AGENT_TIMEOUT。
        """
        if not self.app_key:
            raise DifyError("AGENT_ERROR", "没有配置 KE_DIFY_APP_KEY")
        deadline = deadline if deadline is not None else time.monotonic() + self.timeout_s
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DifyError("AGENT_TIMEOUT", f"智能体用完了 {self.timeout_s} 秒的时间预算")
        body = {"inputs": {}, "query": query, "response_mode": "streaming",
                "conversation_id": conversation_id, "user": user}
        headers = {"Authorization": f"Bearer {self.app_key}"}
        answer: list[str] = []
        thoughts: dict[str, AgentThought] = {}
        conv, msg_id = conversation_id, ""
        try:
            # Dify 流式每 10 秒发一次 ping，单次读超过 30 秒没数据就当断了；所以最多超出预算 30 秒
            timeout = httpx.Timeout(min(30, remaining), connect=min(10, remaining))
            with httpx.stream("POST", f"{self.api_base}/chat-messages", json=body, headers=headers, timeout=timeout) as r:
                if r.status_code != 200:
                    raise DifyError("AGENT_ERROR", f"Dify 返回 HTTP {r.status_code}：{r.read().decode(errors='replace')[:300]}")
                for line in self._lines(r, deadline):
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:].strip() or "{}")
                    kind = ev.get("event")
                    conv = ev.get("conversation_id") or conv
                    msg_id = ev.get("message_id") or msg_id
                    if kind in ("agent_message", "message"):
                        answer.append(ev.get("answer", ""))
                    elif kind == "agent_thought":
                        t = AgentThought(id=ev.get("id", ""), position=ev.get("position", 0),
                                         thought=ev.get("thought") or "", tool=ev.get("tool") or "",
                                         tool_input=ev.get("tool_input") or "",
                                         observation=(ev.get("observation") or "")[:2000])
                        thoughts[t.id] = t
                        if on_thought:
                            on_thought(t)
                    elif kind == "error":
                        raise DifyError("AGENT_ERROR", f"{ev.get('code')}: {ev.get('message')}")
        except httpx.TimeoutException as e:
            raise DifyError("AGENT_TIMEOUT", f"Dify 超过 {self.timeout_s} 秒没有完成：{e}") from e
        except httpx.HTTPError as e:
            raise DifyError("AGENT_ERROR", f"连不上 Dify：{e}") from e
        return ChatResult(answer=strip_think("".join(answer)), conversation_id=conv, message_id=msg_id,
                          thoughts=sorted(thoughts.values(), key=lambda t: t.position))

    def _lines(self, r: httpx.Response, deadline: float):
        """按块读流、自己切行，每收到一块就检查截止时间（不依赖对方发换行）。"""
        buf = ""
        for chunk in r.iter_text():
            if time.monotonic() > deadline:
                raise DifyError("AGENT_TIMEOUT", f"智能体超过 {self.timeout_s} 秒的时间预算还没答完")
            buf += chunk
            *lines, buf = buf.split("\n")
            for line in lines:
                yield line.rstrip("\r")
        if buf:
            yield buf.rstrip("\r")
