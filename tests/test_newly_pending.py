from claude_cockpit.main import newly_pending


def test_new_member_becomes_pending():
    # b 是这一轮新进入「有消息」的成员
    assert newly_pending({"a"}, {"a", "b"}) == {"b"}


def test_no_change_means_nothing_new():
    assert newly_pending({"a", "b"}, {"a", "b"}) == set()


def test_dropped_pending_is_not_new():
    # 方向不能反:从 pending 里消失的不算「新」
    assert newly_pending({"a", "b"}, {"a"}) == set()


def test_all_new_from_empty():
    assert newly_pending(set(), {"a", "b"}) == {"a", "b"}
