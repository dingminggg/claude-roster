"""添加/编辑成员的对话框。返回字段 dict(校验交给调用方),取消返回 None。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton, QWidget,
)

PERMS = ["default", "acceptEdits", "plan", "bypassPermissions"]
MODELS = ["(默认)", "opus", "sonnet", "haiku"]


def member_dialog(parent, member=None) -> dict | None:
    editing = member is not None
    dlg = QDialog(parent)
    dlg.setWindowTitle("编辑成员" if editing else "添加成员")
    form = QFormLayout(dlg)

    name = QLineEdit(member.name if editing else "")
    if editing:
        name.setReadOnly(True)               # 名字不可改(改名=删了重加)
        name.setToolTip("名字不可改;如需改名请删除后重新添加")
    form.addRow("名字", name)

    cwd = QLineEdit(str(member.cwd) if editing else "")
    browse = QPushButton("…")
    browse.setFixedWidth(30)

    def pick():
        d = QFileDialog.getExistingDirectory(dlg, "选择工作目录", cwd.text() or "")
        if d:
            cwd.setText(d.replace("/", "\\"))
    browse.clicked.connect(pick)
    cwd_row = QWidget()
    cl = QHBoxLayout(cwd_row)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.addWidget(cwd)
    cl.addWidget(browse)
    form.addRow("目录", cwd_row)

    emoji = QLineEdit(member.emoji if editing else "🤖")
    form.addRow("Emoji", emoji)
    color = QLineEdit(member.color if editing else "#3b82f6")
    form.addRow("颜色", color)

    model = QComboBox()
    model.addItems(MODELS)
    if editing and member.model:
        if member.model not in MODELS:
            model.addItem(member.model)
        model.setCurrentText(member.model)
    form.addRow("模型", model)

    perm = QComboBox()
    perm.addItems(PERMS)
    perm.setCurrentText(member.permission_mode if editing else "default")
    form.addRow("权限", perm)

    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                          | QDialogButtonBox.StandardButton.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    form.addRow(bb)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    mdl = model.currentText()
    return {
        "name": name.text().strip(),
        "cwd": cwd.text().strip().strip('"'),
        "emoji": emoji.text().strip() or "🤖",
        "color": color.text().strip() or "#3b82f6",
        "model": None if mdl == "(默认)" else mdl,
        "permission_mode": perm.currentText(),
    }
