"""面板:运行键四态(启动/启动中/忙碌中/空闲)+ 右键「复制会话地址」。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from claude_cockpit.config import Member
from claude_cockpit.panel import Panel


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


@pytest.fixture
def panel(app):
    m = Member(name="fad", cwd=Path("."), emoji="🏪", color="#e74c3c")
    return Panel([m])


def _go(panel):
    return panel._gos["fad"]


@pytest.mark.parametrize("state,text", [
    ("down", "启动"),
    ("launching", "启动中"),
    ("busy", "忙碌中"),
    ("idle", "空闲"),
])
def test_capsule_text_per_state(panel, state, text):
    panel.set_run_state("fad", state)
    assert _go(panel).text() == text


def test_unknown_status_falls_back_to_running(panel):
    """探不到会话状态(版本不支持/刚起来)时仍显示「运行中」,不留空白。"""
    panel.set_run_state("fad", "running")
    assert _go(panel).text() == "运行中"


def test_capsule_keeps_one_size_across_states(panel):
    sizes = set()
    for state in ("down", "launching", "busy", "idle", "running"):
        panel.set_run_state("fad", state)
        sizes.add((_go(panel).width(), _go(panel).height()))
    assert len(sizes) == 1


def test_only_down_is_clickable_and_dimmed(panel):
    for state in ("busy", "idle", "running", "launching"):
        panel.set_run_state("fad", state)
        assert not _go(panel).isEnabled()
        assert panel._effects["fad"].opacity() == 1.0
    panel.set_run_state("fad", "down")
    assert _go(panel).isEnabled()
    assert panel._effects["fad"].opacity() < 1.0


def test_busy_and_idle_cards_are_clickable_to_raise(panel):
    """点横条置前只对「起来了」的卡开放,忙/闲都算起来了。"""
    for state in ("busy", "idle", "running"):
        panel.set_run_state("fad", state)
        assert panel._cards["fad"].cursor().shape() == Qt.CursorShape.PointingHandCursor
    for state in ("down", "launching"):
        panel.set_run_state("fad", state)
        assert panel._cards["fad"].cursor().shape() == Qt.CursorShape.ArrowCursor


def test_session_picker_only_when_down(panel):
    """四态改造别把未运行时的会话下拉弄丢了。"""
    panel.set_run_state("fad", "busy")
    assert not panel._pickers["fad"].isVisibleTo(panel)
    panel.set_run_state("fad", "down")
    assert panel._pickers["fad"].isVisibleTo(panel)


def _copy_action(panel):
    menu = panel._cards["fad"].build_menu()
    return next(a for a in menu.actions() if a.text() == "复制会话地址")


def test_copy_address_disabled_until_known(panel):
    assert not _copy_action(panel).isEnabled()


def test_copy_address_enabled_and_emits_name(panel):
    panel.set_address("fad", "fad-backend-f3")
    got = []
    panel.copy_address_requested.connect(got.append)
    act = _copy_action(panel)
    assert act.isEnabled()
    assert "fad-backend-f3" in act.toolTip()
    act.trigger()
    assert got == ["fad"]


def test_clearing_address_disables_again(panel):
    panel.set_address("fad", "fad-backend-f3")
    panel.set_address("fad", None)
    assert not _copy_action(panel).isEnabled()


def test_menu_keeps_existing_items(panel):
    labels = [a.text() for a in panel._cards["fad"].build_menu().actions()]
    for expected in ("打开目录", "编辑", "删除"):
        assert expected in labels
