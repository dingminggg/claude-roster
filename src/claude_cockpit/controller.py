"""轮询状态机(纯逻辑,不碰 Qt/Win32)。

每轮 update(当前 pending 成员名集合) → 返回本轮新出现、需要置前的成员名列表。
"""
from __future__ import annotations


class Controller:
    def __init__(self, member_names: list[str]):
        self._names = list(member_names)
        self._pending: set[str] = set()      # 上一轮 pending 集合

    def set_members(self, member_names: list[str]) -> None:
        """成员增删后更新名单(保持 pending 状态)。"""
        self._names = list(member_names)

    def update(self, pending_now: set[str]) -> list[str]:
        """返回从「无 pending」变成「有 pending」的成员(需置前),保持成员顺序。"""
        newly = pending_now - self._pending
        self._pending = set(pending_now)
        return [n for n in self._names if n in newly]

    def status(self, name: str) -> str:
        return "pending" if name in self._pending else "idle"
