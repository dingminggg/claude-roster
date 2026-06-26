import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from claude_cockpit.panel import TrayPopup


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def test_rows_render_as_clickable_items(app):
    rows = [("alice", "🐸", "#2980b9"), ("bob", "🦊", "#e67e22")]
    pop = TrayPopup(rows)
    items = pop.findChildren(QPushButton)
    assert len(items) == 2
    assert "@alice" in items[0].text()
    assert "@bob" in items[1].text()


def test_click_emits_picked_name(app):
    pop = TrayPopup([("alice", "🐸", "#2980b9")])
    got = []
    pop.picked.connect(got.append)
    pop.findChildren(QPushButton)[0].click()
    assert got == ["alice"]
