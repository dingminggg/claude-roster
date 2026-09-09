"""布局纯逻辑:解析/序列化/补齐缺省/找空位。不依赖 Qt。"""
from pathlib import Path

from claude_cockpit import layout
from claude_cockpit.config import Member


def _m(name, dept=""):
    return Member(name=name, cwd=Path("."), dept=dept)


def test_parse_roundtrip():
    raw = {"areas": {"后端组": [10, 30, 420, 150]}, "seats": {"fad": [20, 26]},
           "window": [900, 620], "zoom": 1.5}
    lay = layout.parse(raw)
    assert lay.areas["后端组"] == (10.0, 30.0, 420.0, 150.0)
    assert lay.seats["fad"] == (20.0, 26.0)
    assert lay.window == (900, 620)
    assert lay.zoom == 1.5
    assert layout.dump(lay) == raw


def test_parse_garbage_is_dropped_not_raised():
    """坏数据一律丢弃回默认:布局是便利功能,不能因为它打不开面板。"""
    lay = layout.parse({"areas": {"x": [1, 2]}, "seats": {"fad": "nope"},
                        "window": "big", "zoom": None})
    assert lay.areas == {} and lay.seats == {}
    assert lay.window == layout.DEFAULT_WINDOW
    assert lay.zoom == 1.0


def test_parse_non_dict():
    assert layout.parse(None).areas == {}
    assert layout.parse([1, 2]).seats == {}


def test_dept_of_falls_back_to_unassigned():
    assert layout.dept_of(_m("fad", "后端组")) == "后端组"
    assert layout.dept_of(_m("fad")) == layout.UNASSIGNED


def test_ensure_creates_area_per_dept_stacked_downwards():
    """两个部门 → 两块地毯,第二块排在第一块下面,不重叠。"""
    lay = layout.ensure(layout.parse({}), [_m("a", "后端组"), _m("b", "客户端组")])
    ax, ay, aw, ah = lay.areas["后端组"]
    bx, by, bw, bh = lay.areas["客户端组"]
    assert (ax, ay) == layout.AREA_ORIGIN
    assert by >= ay + ah


def test_ensure_places_seats_in_grid_inside_area():
    """同部门前两个成员在默认地毯(420x150)里并排;第三个放不下 → 地毯变宽,
    新人贴在原右边界外侧(而不是落在地毯外面)。"""
    lay = layout.ensure(layout.parse({}),
                        [_m("a", "d"), _m("b", "d"), _m("c", "d")])
    assert lay.seats["a"] == layout.AREA_PAD
    assert lay.seats["b"][1] == layout.AREA_PAD[1]
    assert lay.seats["b"][0] > lay.seats["a"][0]
    assert lay.seats["c"][0] > lay.seats["b"][0]
    w = lay.areas["d"][2]
    assert w > layout.AREA_DEFAULT[0]
    assert lay.seats["c"][0] + layout.SEAT_W <= w


def test_ensure_wraps_to_second_row_when_area_is_tall():
    """地毯够高时按行优先铺:第三个换到第二排,不是把地毯越拉越宽。"""
    lay = layout.parse({"areas": {"d": [0, 0, 420, 300]}})
    lay = layout.ensure(lay, [_m("a", "d"), _m("b", "d"), _m("c", "d")])
    assert lay.seats["c"][1] > lay.seats["b"][1]
    assert lay.seats["c"][0] == layout.AREA_PAD[0]
    assert lay.areas["d"][2] == 420.0        # 宽度没被动过


def test_ensure_grows_area_when_no_slot_left():
    """手调过的小区域塞不下新人 → 区域向右撑大,新人不许落在地毯外。"""
    lay = layout.parse({"areas": {"d": [0, 0, 200, 120]}, "seats": {"a": [20, 26]}})
    lay = layout.ensure(lay, [_m("a", "d"), _m("b", "d")])
    x, y, w, h = lay.areas["d"]
    bx, by = lay.seats["b"]
    assert w > 200
    assert bx + layout.SEAT_W <= w
    assert by + layout.SEAT_H <= h


def test_ensure_keeps_existing_positions():
    """用户摆好的位置不许被 ensure 挪动。"""
    lay = layout.parse({"areas": {"d": [7, 9, 420, 150]}, "seats": {"a": [111, 77]}})
    lay = layout.ensure(lay, [_m("a", "d")])
    assert lay.seats["a"] == (111.0, 77.0)
    assert lay.areas["d"] == (7.0, 9.0, 420.0, 150.0)


def test_ensure_drops_areas_and_seats_of_gone_members():
    """成员/部门删了之后,残留坐标不该继续留在文件里。"""
    lay = layout.parse({"areas": {"d": [0, 0, 420, 150], "old": [0, 200, 420, 150]},
                        "seats": {"a": [20, 26], "ghost": [220, 26]}})
    lay = layout.ensure(lay, [_m("a", "d")])
    assert set(lay.areas) == {"d"}
    assert set(lay.seats) == {"a"}
