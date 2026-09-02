"""标题匹配必须按「完整名字」命中:CCKPT:fad 不能抓到 CCKPT:fad-3 的窗口。
(历史 bug:子串匹配让 fad 偷走了 fad-3 的句柄,两成员指向同一控制台。)"""
from claude_cockpit.winman import title_matches
from claude_cockpit.store import dedupe


def test_exact_title_matches():
    assert title_matches("CCKPT:fad", "CCKPT:fad")


def test_prefix_of_sibling_does_not_match():
    assert not title_matches("CCKPT:fad-3", "CCKPT:fad")
    assert not title_matches("CCKPT:fad2", "CCKPT:fad")
    assert not title_matches("CCKPT:fad_x", "CCKPT:fad")


def test_allows_host_decoration_around_name():
    # 管理员控制台 / 终端会在标题前后加装饰,只要名字本身完整就算命中
    assert title_matches("Administrator: CCKPT:fad", "CCKPT:fad")
    assert title_matches("CCKPT:fad - cmd", "CCKPT:fad")


def test_needle_absent():
    assert not title_matches("Claude Code", "CCKPT:fad")


def test_dedupe_keeps_first_owner_of_shared_hwnd():
    # 同一句柄被两个成员缓存时,只认最早写入的那个(后来者是误抓)
    assert dedupe({"fad-3": 263952, "fad": 263952, "x": 1}) == {"fad-3": 263952, "x": 1}
