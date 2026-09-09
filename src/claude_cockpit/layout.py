"""办公室画布的布局:哪块地毯在哪、哪个工位摆在地毯的哪个位置。

坐标落在 settings.json 的 `office` 段。**工位坐标是「相对所属部门区域」的偏移**
(工位是区域的 Qt 子项),区域坐标是绝对值——这样整块地毯挪走时工位不用重算。

本模块是纯逻辑,不 import Qt:布局能单独测,面板只管把结果摆上去。
坏数据一律丢弃回默认(与 peers.py 同口径):布局是便利功能,不能因为它打不开面板。
"""
from __future__ import annotations

from dataclasses import dataclass, field

SEAT_W, SEAT_H = 180, 112
GAP = 20                        # 工位之间的间距
AREA_PAD = (20.0, 26.0)         # 区域内第一个工位的左上留白(26 让开地毯上的部门名)
AREA_MIN = (200.0, 120.0)       # 区域最小尺寸(与 DeptAreaItem 的拉伸下限一致)
AREA_DEFAULT = (420.0, 150.0)   # 一块地毯至少这么大(一排两个工位)
AREA_COLS = 3                   # 新地毯按几列铺:再宽一屏就装不下了
AREA_ORIGIN = (10.0, 30.0)      # 第一块地毯的落点
DEFAULT_WINDOW = (900, 620)
UNASSIGNED = "未分配"           # 没填 dept 的成员归到这块地毯


@dataclass
class Layout:
    areas: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    seats: dict[str, tuple[float, float]] = field(default_factory=dict)
    window: tuple[int, int] = DEFAULT_WINDOW
    zoom: float = 1.0


def dept_of(member) -> str:
    return member.dept.strip() or UNASSIGNED


def _nums(v, n):
    """把 v 解析成 n 个 float;形状不对返回 None(调用方丢弃这条)。"""
    if not isinstance(v, (list, tuple)) or len(v) != n:
        return None
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        out.append(float(x))
    return tuple(out)


def _items(raw, key):
    """raw[key] 是 dict 才遍历,否则当空的(坏数据不抛,直接丢)。"""
    v = raw.get(key)
    return v.items() if isinstance(v, dict) else ()


def parse(raw) -> Layout:
    if not isinstance(raw, dict):
        return Layout()
    areas, seats = {}, {}
    for k, v in _items(raw, "areas"):
        got = _nums(v, 4)
        if got and got[2] >= AREA_MIN[0] and got[3] >= AREA_MIN[1]:
            areas[str(k)] = got
    for k, v in _items(raw, "seats"):
        got = _nums(v, 2)
        if got:
            seats[str(k)] = got
    win = _nums(raw.get("window"), 2)
    zoom = raw.get("zoom")
    return Layout(
        areas=areas,
        seats=seats,
        window=(int(win[0]), int(win[1])) if win else DEFAULT_WINDOW,
        zoom=float(zoom) if isinstance(zoom, (int, float))
        and not isinstance(zoom, bool) and 0.2 <= zoom <= 4 else 1.0,
    )


def dump(lay: Layout) -> dict:
    return {
        "areas": {k: [_i(v[0]), _i(v[1]), _i(v[2]), _i(v[3])]
                  for k, v in lay.areas.items()},
        "seats": {k: [_i(v[0]), _i(v[1])] for k, v in lay.seats.items()},
        "window": [int(lay.window[0]), int(lay.window[1])],
        "zoom": lay.zoom,
    }


def _i(x: float):
    """整数就存整数:settings.json 里不留 20.0 这种噪声。"""
    return int(x) if float(x).is_integer() else float(x)


def _default_area_size(n: int) -> tuple[float, float]:
    """新地毯的尺寸:按人数铺成最多 AREA_COLS 列的网格。

    不这么算就得靠 ensure 一个个向右撑宽,13 个人会变成一条两千多像素的窄带,
    一屏根本看不完。
    """
    cols = max(1, min(AREA_COLS, n))
    rows = max(1, -(-n // cols))            # 向上取整
    w = AREA_PAD[0] * 2 + cols * SEAT_W + (cols - 1) * GAP
    h = AREA_PAD[1] + rows * SEAT_H + (rows - 1) * GAP + AREA_PAD[1]
    return (max(AREA_DEFAULT[0], w), max(AREA_DEFAULT[1], h))


def _slots(w: float, h: float):
    """区域里能放下的工位位置,按行优先。"""
    y = AREA_PAD[1]
    while y + SEAT_H <= h:
        x = AREA_PAD[0]
        while x + SEAT_W <= w:
            yield (x, y)
            x += SEAT_W + GAP
        y += SEAT_H + GAP


def ensure(lay: Layout, members) -> Layout:
    """补齐缺失的地毯和工位坐标,并丢掉已删成员/空部门的残留。

    已有的坐标一律保持原样——用户摆好的位置不许被程序挪动。
    """
    depts, by_dept = [], {}
    for m in members:
        d = dept_of(m)
        if d not in by_dept:
            depts.append(d)
            by_dept[d] = []
        by_dept[d].append(m.name)

    areas = {d: lay.areas[d] for d in depts if d in lay.areas}
    for d in depts:
        if d in areas:
            continue
        bottom = max((y + h for _x, y, _w, h in areas.values()), default=None)
        y = AREA_ORIGIN[1] if bottom is None else bottom + GAP
        aw, ah = _default_area_size(len(by_dept[d]))
        areas[d] = (AREA_ORIGIN[0], y, aw, ah)

    seats = {}
    for d in depts:
        x, y, w, h = areas[d]
        taken = set()
        for name in by_dept[d]:
            if name in lay.seats:
                seats[name] = lay.seats[name]
                taken.add(lay.seats[name])
        for name in by_dept[d]:
            if name in seats:
                continue
            spot = next((s for s in _slots(w, h) if s not in taken), None)
            if spot is None:
                # 区域塞不下了(地毯太矮,或者用户手动缩小过):向右撑大一格,
                # 别让新人落在地毯外面
                spot = (_grow_x(w), AREA_PAD[1])
                w = spot[0] + SEAT_W + AREA_PAD[0]
                h = max(h, AREA_PAD[1] + SEAT_H + AREA_PAD[1])
                areas[d] = (x, y, w, h)
            seats[name] = spot
            taken.add(spot)
    return Layout(areas=areas, seats=seats, window=lay.window, zoom=lay.zoom)


def _grow_x(w: float) -> float:
    """撑大区域时新工位的落点:紧贴原右边界外侧。"""
    return max(AREA_PAD[0], w - AREA_PAD[0] + GAP)
