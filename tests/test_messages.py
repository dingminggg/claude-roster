"""会话之间发消息 → 小人跑一趟:信号通道、hook、画布三段各测一遍。"""
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
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
    # 对话记录也要隔离:OfficeWindow 一建就 refresh_history,不打桩的话
    # 用例会去读开发机上真实的 history.jsonl(那里面真有 cwd 归一后
    # 和测试员工撞上的记录),结果随机器而变。只读不写,指到 tmp 即可。
    monkeypatch.setattr(cc_signals, "history_path",
                        lambda: tmp_path / "history.jsonl")
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


def _run(w, ms):
    """跑够 ms 毫秒(图元被摘掉就停)。"""
    from claude_cockpit.office import walker_item as wi
    for _ in range(int(ms // wi.TICK_MS) + 1):
        if w.scene() is None:
            return
        w._step()


def _until(w, phase, cap_ms=30000):
    """一直跑到进入 `phase` 那一拍——各拍时长不一样,按毫秒硬算容易多跑一拍。"""
    from claude_cockpit.office import walker_item as wi
    for _ in range(int(cap_ms // wi.TICK_MS)):
        if w._phase == phase or w.scene() is None:
            return
        w._step()


def test_walker_walks_then_disappears(app, office):
    """走过去 → 开窗打字 → 停住让人读 → 收窗 → 走回来 → 自己从场景里消失。"""
    from claude_cockpit.office import walker_item as wi
    office.send_walker("fad", "etl", "改好了")
    w = office._walkers[0]
    start = w.pos()
    _run(w, wi.OUT_MS)
    assert w.pos() != start and not w.is_walking()       # 到了,站住说话
    _run(w, wi.OPEN_MS + w._type_ms + w._hold_ms + wi.CLOSE_MS + wi.OUT_MS + 200)
    assert w.scene() is None                             # 走完自己摘掉


def test_the_window_opens_then_types_then_holds(app, office):
    """四拍:开窗 → 一个字一个字打 → 停住让人读 → 收窗。"""
    from claude_cockpit.office import walker_item as wi
    office.send_walker("fad", "etl", "改好了")
    w = office._walkers[0]
    _run(w, wi.OUT_MS)
    assert w._phase == "open" and w._grow() < 1.0        # 窗口先展开,字还没出
    _until(w, "type")
    assert w._phase == "type"
    first = w._reveal()
    _run(w, wi.TYPE_MS_PER_CHAR * 2)
    assert w._reveal() > first                           # 字在一个个往外冒
    _until(w, "hold")
    assert w._reveal() == w._chars                       # 打完了,全文停住
    assert w._hold_ms == wi.HOLD_MS                      # 停 5 秒让人读完
    _until(w, "close")
    w._step()                                            # 刚进这一拍时还是满格
    assert w._grow() < 1.0                               # 再收回去


def test_walking_is_slow_enough_to_notice(app, office):
    """走得慢一点:1.5 秒那版像在赶路,一眼扫过去只看见有东西闪过。"""
    from claude_cockpit.office import walker_item as wi
    assert wi.OUT_MS >= 2500


def test_a_wordless_message_does_not_hold_for_five_seconds(app, office):
    """没正文时只冒三个点,没什么可读的,不用停这么久。"""
    from claude_cockpit.office import walker_item as wi
    office.send_walker("fad", "etl")
    w = office._walkers[0]
    assert w._chars == 0 and w._hold_ms == wi.DOTS_HOLD_MS


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


# ---------- 气泡里的话 ----------
def test_hook_records_the_message_body(tmp_path, monkeypatch):
    """气泡要显示「说了什么」,所以 hook 得把正文也记一笔。"""
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    message_sent.handle({"tool_name": "SendMessage", "cwd": r"C:\proj\fad",
                         "tool_input": {"to": "etl-7a", "message": "帮我跑一下 ETL"}})
    got = cc_signals.take_messages()
    assert got[0]["text"] == "帮我跑一下 ETL"


def test_body_is_truncated_and_flattened_on_write(tmp_path, monkeypatch):
    """换行压成空格(气泡自己排版)、超长在写入侧就截断(整篇正文既画不下也不必落盘)。"""
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    cc_signals.write_message(r"C:\proj\fad", "etl-7a", "第一行\n第二行\t还有" + "啊" * 300)
    text = cc_signals.take_messages()[0]["text"]
    assert "\n" not in text and "第一行 第二行 还有" in text
    assert len(text) == cc_signals.MSG_MAX


def test_old_signals_without_a_body_still_work(tmp_path, monkeypatch):
    """没正文的老信号(或空消息)不能崩,退回原来那三个点。"""
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    cc_signals.write_message(r"C:\proj\fad", "etl-7a")
    assert cc_signals.take_messages()[0]["text"] == ""


def test_wrap_folds_by_pixel_width_not_character_count(app):
    """按字宽折:中文一个字是英文的两倍宽,按字数折两种话会排成完全不同的长度。"""
    from claude_cockpit.office import bubble
    assert bubble.wrap("") == []
    assert bubble.wrap("短") == ["短"]
    many = bubble.wrap("啊" * 200)
    assert len(many) == bubble.MAX_LINES and many[-1].endswith("…")
    for line in many:
        assert bubble.FM.horizontalAdvance(line) <= bubble.W - bubble.PAD * 2


def test_bubble_grows_with_the_text(app, office):
    from claude_cockpit.office import walker_item as wi
    quiet = wi.WalkerItem(QColor("#888"), [QPointF(0, 0), QPointF(10, 0)])
    talky = wi.WalkerItem(QColor("#888"), [QPointF(0, 0), QPointF(10, 0)],
                          "帮我把 ETL 重跑一遍,顺便看看昨天那批数据")
    assert talky._bh > quiet._bh
    # 包围盒跟着气泡长,否则长气泡会被裁掉一块
    assert talky.boundingRect().height() > quiet.boundingRect().height()
    # 打字那一拍按字数算:话越长,打得越久
    assert talky._type_ms > quiet._type_ms


def test_walker_paints_its_bubble(app, office):
    from PySide6.QtGui import QImage, QPainter
    from claude_cockpit.office import walker_item as wi
    for text in ("", "跑完了", "啊" * 200):
        w = wi.WalkerItem(QColor("#888"), [QPointF(0, 0), QPointF(10, 0)], text)
        w._phase = "wait"
        img = QImage(240, 200, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        try:
            w.paint(p, None, None)
        finally:
            p.end()


def test_the_body_reaches_the_walker(app, office):
    office.send_walker("fad", "etl", "改好了")
    assert office._walkers[-1]._lines == ["改好了"]
