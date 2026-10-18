"""Dify chat-messages 流式客户端（旧式 Agent 应用）。

按 Dify 1.17.1 的事件定义写成：agent_thought（按 id 合并）、agent_message/message（答案分片）、
message_end（拿 conversation_id）、error。块 1 第 1 周用真实应用联调确认，接口不变。
"""
import json
from dataclasses import dataclass, field
from typing import Callable

import httpx

from app.config import AGENT_TIMEOUT_S, DIFY_API_BASE, DIFY_APP_KEY
from app.schemas import AgentThought


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
             on_thought: Callable[[AgentThought], None] | None = None) -> ChatResult:
        """发一条消息并等完整回答。user 固定用 f"task-{task_id}"，追问时必须和第一次相同"""
        if not self.app_key:
            raise DifyError("AGENT_ERROR", "没有配置 KE_DIFY_APP_KEY")
        body = {"inputs": {}, "query": query, "response_mode": "streaming",
                "conversation_id": conversation_id, "user": user}
        headers = {"Authorization": f"Bearer {self.app_key}"}
        answer: list[str] = []
        thoughts: dict[str, AgentThought] = {}
        conv, msg_id = conversation_id, ""
        try:
            timeout = httpx.Timeout(self.timeout_s, connect=10)
            with httpx.stream("POST", f"{self.api_base}/chat-messages", json=body, headers=headers, timeout=timeout) as r:
                if r.status_code != 200:
                    raise DifyError("AGENT_ERROR", f"Dify 返回 HTTP {r.status_code}：{r.read().decode(errors='replace')[:300]}")
                for line in r.iter_lines():
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
        return ChatResult(answer="".join(answer), conversation_id=conv, message_id=msg_id,
                          thoughts=sorted(thoughts.values(), key=lambda t: t.position))
