"""对话记录窗:内容、方向、空记录、转义。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from claude_cockpit.history import Entry
from claude_cockpit.office.history_popup import HistoryPopup


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _entries():
    return [
        Entry("out", "etl", "跑一下昨天的单子", 1757800000.0),
        Entry("in", "etl", "跑完了,3 条异常", 1757800600.0),
    ]


def test_shows_both_directions(app):
    w = HistoryPopup("fad", _entries())
    text = w.body.toPlainText()
    assert "跑一下昨天的单子" in text and "跑完了,3 条异常" in text
    assert "→ etl" in text and "← etl" in text


def test_newest_at_bottom(app):
    w = HistoryPopup("fad", _entries())
    text = w.body.toPlainText()
    assert text.index("跑一下昨天的单子") < text.index("跑完了")


def test_is_popup_and_selectable(app):
    w = HistoryPopup("fad", _entries())
    assert w.windowFlags() & Qt.WindowType.Popup
    assert w.body.isReadOnly()
    assert w.body.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse


def test_empty_entries_say_so(app):
    w = HistoryPopup("fad", [])
    assert "还没有" in w.body.toPlainText()


def test_escapes_html(app):
    w = HistoryPopup("fad", [Entry("out", "etl", "<b>不要加粗</b>", 1757800000.0)])
    assert "<b>不要加粗</b>" in w.body.toPlainText()


def test_long_text_not_truncated(app):
    """正文是完整存下来的(最长 2000 字),记录窗别自作主张截断——
    截断是气泡的事,记录窗就是来看全文的。"""
    long = "字" * 1500
    w = HistoryPopup("fad", [Entry("in", "etl", long, 1757800000.0)])
    assert long in w.body.toPlainText()
