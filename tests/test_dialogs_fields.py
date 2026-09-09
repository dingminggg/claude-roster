"""成员对话框:部门字段能带进去、能取出来(不 exec,直接查表单构造)。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from claude_cockpit import dialogs
from claude_cockpit.config import Member


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def test_dialog_returns_dept(app, monkeypatch):
    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    m = Member(name="fad", cwd=Path("."), dept="后端组")
    data = dialogs.member_dialog(None, m)
    assert data["dept"] == "后端组"


def test_dialog_dept_defaults_empty_for_new(app, monkeypatch):
    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    assert dialogs.member_dialog(None)["dept"] == ""
