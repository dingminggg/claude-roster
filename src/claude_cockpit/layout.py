"""办公室画布的布局:哪块地毯在哪、哪个工位摆在地毯的哪个位置。

坐标落在 settings.json 的 `office` 段。**工位坐标是「相对所属部门区域」的偏移**
(工位是区域的 Qt 子项),区域坐标是绝对值——这样整块地毯挪走时工位不用重算。

本模块是纯逻辑,不 import Qt:布局能单独测,面板只管把结果摆上去。
坏数据一律丢弃回默认(与 peers.py 同口径):布局是便利功能,不能因为它打不开面板。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 工位尺寸是**这里说了算**:office/seat_item.py 从这儿 import,
# 布局算账和绘制才不会各持一份、悄悄对不上。
SEAT_W, SEAT_H = 200, 146
GAP = 16                        # 工位之间的间距
AREA_PAD = (18.0, 26.0)         # 区域内第一个工位的左上留白(26 让开地毯上的部门名)
AREA_MIN = (240.0, 200.0)       # 区域最小尺寸(装得下一个工位 + 留白)
AREA_DEFAULT = (452.0, 200.0)   # 一块地毯至少这么大(一排两个工位)
AREA_COLS = 3                   # 新地毯按几列铺:再宽一屏就装不下了
AREA_ORIGIN = (10.0, 30.0)      # 第一块地毯的落点
DEFAULT_WINDOW = (900, 620)
UNASSIGNED = "未分配"           # 没填 dept 的员工归到这块部门区
SERVER_ROOM = "运维"           # 运维那个固定岗位所在的部门区(见 config.OPS_DEPT)
# 曾经用过的前缀:机柜当过独立图元、按「占位成员」参与布局。现在机柜是运维**桌上
# 的一样家具**,不占格子也不存坐标;这个常量只留给老 settings.json —— 里面可能还
# 躺着 svc:rack 之类的键,认出来好丢掉(layout.ensure 本来就会丢,这里只是留个名)。
SVC_PREFIX = "svc:"


@dataclass
class Layout:
    areas: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    seats: dict[str, tuple[float, float]] = field(default_factory=dict)
    # 每个工位自己的缩放:成员多了,不常用的可以单独缩小。缺省 1.0 不落盘。
    scales: dict[str, float] = field(default_factory=dict)
    # 用户手工建出来的部门(可能还一个人都没有)。不记这份名单的话,
    # 「先建好空地毯、再把人拖进去」这个流程第一步就没了——ensure 会把没人的
    # 地毯当残留清掉。
    depts: list[str] = field(default_factory=list)
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
    scales = {}
    for k, v in _items(raw, "seats"):
        # 老文件是 [x, y];带缩放的是 [x, y, scale]。两种都认。
        got = _nums(v, 2) or _nums(v, 3)
        if not got:
            continue
        seats[str(k)] = got[:2]
        if len(got) == 3 and 0.2 <= got[2] <= 1.0:
            scales[str(k)] = got[2]
    depts = [str(d) for d in raw.get("depts") or [] if isinstance(d, str)]
    win = _nums(raw.get("window"), 2)
    zoom = raw.get("zoom")
    return Layout(
        areas=areas,
        seats=seats,
        scales=scales,
        depts=depts,
        window=(int(win[0]), int(win[1])) if win else DEFAULT_WINDOW,
        zoom=float(zoom) if isinstance(zoom, (int, float))
        and not isinstance(zoom, bool) and 0.2 <= zoom <= 4 else 1.0,
    )


def dump(lay: Layout) -> dict:
    return {
        "areas": {k: [_i(v[0]), _i(v[1]), _i(v[2]), _i(v[3])]
                  for k, v in lay.areas.items()},
        "seats": {k: ([_i(v[0]), _i(v[1])] if lay.scales.get(k, 1.0) == 1.0
                      else [_i(v[0]), _i(v[1]), lay.scales[k]])
                  for k, v in lay.seats.items()},
        "depts": list(lay.depts),
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


def snap_to_slot(pos, area_wh, taken=()) -> tuple[float, float]:
    """把拖到 pos 的工位咬到**最近的空槽位**(槽位就是自动布局用的那套行列)。

    只吸附不代表限制自由:槽位是按 SEAT + GAP 铺的,拖到哪一格就归哪一格,
    松手自动对齐;已经被别人占着的格子会跳过,所以工位不会叠在一起。
    地毯太小一个槽位都没有 → 原样返回,别把工位甩到 (0,0)。
    """
    slots = list(_slots(*area_wh))
    if not slots:
        return (float(pos[0]), float(pos[1]))
    busy = [(float(x), float(y)) for x, y in taken]

    def occupied(slot):
        return any(abs(slot[0] - bx) < 1 and abs(slot[1] - by) < 1
                   for bx, by in busy)

    free = [s for s in slots if not occupied(s)] or slots
    return min(free, key=lambda s: (s[0] - pos[0]) ** 2 + (s[1] - pos[1]) ** 2)


def ensure(lay: Layout, members) -> Layout:
    """补齐缺失的地毯和工位坐标,并丢掉已删成员/空部门的残留。

    已有的坐标一律保持原样——用户摆好的位置不许被程序挪动。
    """
    depts, by_dept = [], {}
    for d in lay.depts:                 # 用户建的空部门也要有地毯
        if d not in by_dept:
            depts.append(d)
            by_dept[d] = []
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
    return Layout(areas=areas, seats=seats,
                  scales={k: v for k, v in lay.scales.items() if k in seats},
                  depts=depts, window=lay.window, zoom=lay.zoom)


def _grow_x(w: float) -> float:
    """撑大区域时新工位的落点:紧贴原右边界外侧。"""
    return max(AREA_PAD[0], w - AREA_PAD[0] + GAP)
