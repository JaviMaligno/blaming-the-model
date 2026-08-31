"""Ordered record of what a classification run did.

Events are appended in the order they happen and can be dumped as JSON Lines.
The kinds in use are ``input``, ``tool_call``, ``tool_result``,
``context_documents``, ``model_message``, ``budget`` and ``final``.
"""

import json

from pydantic import BaseModel


class TraceEvent(BaseModel):
    seq: int
    kind: str
    payload: dict


class Trace:
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def record(self, kind: str, **payload: object) -> None:
        self._events.append(TraceEvent(seq=len(self._events), kind=kind, payload=dict(payload)))

    def to_jsonl(self) -> str:
        return "".join(f"{json.dumps(e.model_dump(), ensure_ascii=False)}\n" for e in self._events)
