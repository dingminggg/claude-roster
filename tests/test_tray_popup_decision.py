from claude_cockpit.main import tray_popup_decision as D

LIMIT = 2


def test_no_pending_hides_when_visible():
    assert D(False, True, True, True, 0, LIMIT) == "hide"


def test_no_pending_noop_when_hidden():
    assert D(False, False, False, False, 0, LIMIT) == "none"


def test_over_icon_shows_when_hidden():
    assert D(True, True, False, False, 0, LIMIT) == "show"


def test_over_icon_noop_when_already_visible():
    assert D(True, True, False, True, 0, LIMIT) == "none"


def test_on_popup_keeps_open():
    # 光标移到浮层上(不在图标)→ 不关
    assert D(True, False, True, True, 0, LIMIT) == "none"


def test_grace_before_hide():
    # 离开图标和浮层,但 miss 还没到阈值 → 暂不关
    assert D(True, False, False, True, 1, LIMIT) == "none"


def test_hide_after_miss_limit():
    assert D(True, False, False, True, 2, LIMIT) == "hide"


def test_hidden_and_not_over_icon_noop():
    assert D(True, False, False, False, 0, LIMIT) == "none"
