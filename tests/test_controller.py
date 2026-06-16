from claude_cockpit.controller import Controller


def test_new_pending_triggers_raise():
    c = Controller(["alpha", "beta"])
    to_raise = c.update({"alpha"})
    assert to_raise == ["alpha"]
    assert c.status("alpha") == "pending"
    assert c.status("beta") == "idle"


def test_same_pending_does_not_retrigger():
    c = Controller(["alpha"])
    assert c.update({"alpha"}) == ["alpha"]
    assert c.update({"alpha"}) == []      # 仍在 pending,不重复置前


def test_cleared_then_new_retriggers():
    c = Controller(["alpha"])
    c.update({"alpha"})
    assert c.update(set()) == []          # 清除
    assert c.status("alpha") == "idle"
    assert c.update({"alpha"}) == ["alpha"]  # 再次出现,重新置前


def test_multiple_new():
    c = Controller(["a", "b", "c"])
    assert set(c.update({"a", "c"})) == {"a", "c"}
    assert c.status("b") == "idle"
