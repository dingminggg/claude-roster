"""会话之间发消息 → 小人跑一趟:信号通道、hook、画布三段各测一遍。"""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from claude_cockpit import cc_signals
from claude_cockpit.config import Member
from claude_cockpit.hooks import message_sent
from claude_cockpit.office.view import OfficeWindow


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def office(app, tmp_path, monkeypatch):
    from claude_cockpit import settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    return OfficeWindow([
        Member(name="fad", cwd=Path("."), emoji="🏪", color="#e74c3c", dept="后端组"),
        Member(name="etl", cwd=Path("."), emoji="🧪", color="#22c55e", dept="后端组"),
    ])


def test_messages_are_events_not_state(tmp_path, monkeypatch):
    """同一个会话连发两条不能互相覆盖(pending 那种按 session_id 覆盖的写法不适用)。"""
    d = tmp_path / "messages"
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: d)
    cc_signals.write_message(r"C:\proj\fad", "fad-backend-2-f3")
    cc_signals.write_message(r"C:\proj\fad", "etl-7a")
    got = cc_signals.take_messages()
    assert [r["to_name"] for r in got] == ["fad-backend-2-f3", "etl-7a"]


def test_take_messages_consumes(tmp_path, monkeypatch):
    """读一次就删:动画演过就完了,再读一遍会重复演。"""
    d = tmp_path / "messages"
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: d)
    cc_signals.write_message(r"C:\proj\fad", "etl-7a")
    assert len(cc_signals.take_messages()) == 1
    assert cc_signals.take_messages() == []


def test_stale_messages_dropped(tmp_path, monkeypatch):
    """驾驶舱没开着时攒下的不补演——开面板时一窝蜂全跑起来没意义。"""
    d = tmp_path / "messages"
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: d)
    cc_signals.write_message(r"C:\proj\fad", "etl-7a")
    assert cc_signals.take_messages(max_age_seconds=-1) == []
    assert not list(d.glob("*.json"))        # 丢掉的也要删,别越攒越多


def test_missing_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "nope")
    assert cc_signals.take_messages() == []


def test_hook_only_fires_for_send_message(tmp_path, monkeypatch):
    d = tmp_path / "messages"
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: d)
    message_sent.handle({"tool_name": "Bash", "cwd": r"C:\proj\fad",
                         "tool_input": {"to": "etl-7a"}})
    assert cc_signals.take_messages() == []
    message_sent.handle({"tool_name": "SendMessage", "cwd": r"C:\proj\fad",
                         "tool_input": {"to": "etl-7a", "message": "hi"}})
    got = cc_signals.take_messages()
    assert got and got[0]["from_cwd"] == r"C:\proj\fad" and got[0]["to_name"] == "etl-7a"


def test_hook_survives_garbage(tmp_path, monkeypatch):
    """hook 绝不能抛:抛了会打断 Claude 那边的工具调用。"""
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    message_sent.handle({})
    message_sent.handle({"tool_name": "SendMessage"})
    message_sent.handle({"tool_name": "SendMessage", "tool_input": "not-a-dict"})
    message_sent.handle({"tool_name": "SendMessage", "tool_input": {"to": ""}, "cwd": ""})
    assert cc_signals.take_messages() == []


def test_send_walker_needs_two_known_seats(app, office):
    assert office.send_walker("fad", "etl") is True
    assert office.send_walker("fad", "fad") is False        # 自己给自己发不演
    assert office.send_walker("fad", "查无此人") is False
    assert office.send_walker("查无此人", "etl") is False


def test_walkers_are_capped(app, office):
    """一屋子人乱窜反而看不出谁找谁,超过上限就不再放人。"""
    for _ in range(office.MAX_WALKERS + 3):
        office.send_walker("fad", "etl")
    assert len(office._walkers) == office.MAX_WALKERS


def test_rebuild_drops_walkers(app, office):
    """rebuild 会 scene.clear():走着的小人已经被删了,名单也得跟着清,不能留野指针。"""
    office.send_walker("fad", "etl")
    assert office._walkers
    office.rebuild(office._members)
    assert office._walkers == []


def test_walker_walks_then_disappears(app, office):
    """走过去 → 停下说话 → 走回来 → 自己从场景里消失。"""
    from claude_cockpit.office import walker_item
    office.send_walker("fad", "etl")
    w = office._walkers[0]
    start = w.pos()
    for _ in range(walker_item.OUT_MS // walker_item.TICK_MS + 1):
        w._step()
    assert w.pos() != start and not w.is_walking()       # 到了,站住说话
    for _ in range((walker_item.WAIT_MS + walker_item.OUT_MS)
                   // walker_item.TICK_MS + 4):
        w._step()
    assert w.scene() is None                             # 走完自己摘掉


def test_walk_path_goes_around_desks(app, office):
    """路线不能两点直连:那样会从桌面上横穿过去。中间必须先退到工位前面的过道。"""
    a, b = office.seats["fad"], office.seats["etl"]
    path = office._walk_path(a, b)
    assert len(path) >= 4                                   # 起点 + 过道两点 + 落点
    lane = office._lane_y(a)
    assert path[1].x() == path[0].x() and path[1].y() == lane      # 先原地往前退到过道
    assert path[2].y() == lane                                     # 再沿过道横着走
    assert lane > path[0].y() and lane > path[-1].y()              # 过道在两把椅子前面


def test_walker_moves_by_arc_length(app, office):
    """取点按**路程**比例,不按段数:不然长段走得飞快、短段磨蹭,一趟路好几种速度。"""
    office.send_walker("fad", "etl")
    w = office._walkers[0]
    path = w._path

    def dist(a, b):
        return ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5

    total = sum(dist(path[i], path[i + 1]) for i in range(len(path) - 1))
    half = w._lerp(0.5)                         # 走到一半时该在的位置
    walked = 0.0
    for i in range(len(path) - 1):
        seg = dist(path[i], path[i + 1])
        if walked + seg >= total / 2:
            k = (total / 2 - walked) / seg
            want_x = path[i].x() + (path[i + 1].x() - path[i].x()) * k
            want_y = path[i].y() + (path[i + 1].y() - path[i].y()) * k
            assert abs(half.x() - want_x) < 0.5 and abs(half.y() - want_y) < 0.5
            return
        walked += seg
    raise AssertionError("没走到一半")
