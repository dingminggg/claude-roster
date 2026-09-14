"""桌上那台小机柜:本地服务(mysql / redis / apache)的状态灯。

**它不是独立图元,是工位上的一样家具**——摆在运维桌上、显示器右边,和音响、杯子、
那叠文件一个级别。曾经是占一整格的落地大机柜(还配了「运维走过去看一眼」的动画),
搬到桌上之后那趟路就没意义了:柜子就在他手边。所以这里只导出**画法和命中区**,
由 `seat_item` 在运维那张工位上调用;状态变了他在工位上冒个气泡说一句。

**一台机柜装下所有服务**。层高是被「层上要印得下服务名」倒推的:柜门在 ISO_FX
面上,那个面的纵轴 1 个单位 = 1 屏幕像素,所以字有多高、层就至少有多厚。

状态语义和工位「屏幕色 = 运行状态」完全一致:绿 = 端口听得到、灭 = 没在跑、
琥珀半拍一闪 = 端口在但不搭理你。画面上不写状态文字,文字版在悬停提示里。

**只读**:点它不启停服务(要管理员权限,而且看板上误点一下就把 MySQL 关了)。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from ..services import DOWN, STUCK, UP
from .iso import ISO_FX, ISO_TEXT_FX, ISO_TEXT_TOP
from .iso import pt as _pt
from .iso import on as _on          # 用工位那套固定原点:柜子就摆在工位的桌面上
from .iso import quad as _quad
from .theme import (
    LED_DOWN, LED_STUCK, LED_UP, RACK, RACK_NAME, RACK_OFF, RACK_SIDE,
    RACK_SLOT, RACK_TOP, mix,
)

# 桌上那台小机柜的房间尺寸和落点。摆在**显示器右边**(x 大那头)、桌面上(z=26)。
# 尺寸得压得够小:它是桌上的一样东西,大了就又变回落地机柜、把显示器比下去。
RX, RY, RZ = 19.0, 18.0, 34.0
RACK_X, RACK_Y, RACK_Z = 42.0, 2.0, 26.0        # 桌面在 z=26
# 尺寸 = **办公桌右半边那块桌面**(显示器右边到桌子右端,连桌子的整个进深):
# 小了就是个不起眼的盒子,看不出是机柜。
# **这个尺寸下屏风上那块名牌保不住**:柜子进深占满桌子,它的左下轮廓会整个扫过
# 屏风(等距下 y 变大 = 往左前走),名字缩到哪儿都会被盖掉——试过把名牌右边界卡到
# 柜子的 x 上,结果柜子顶面的左角比那还靠左,照样盖。所以工位名改**印在柜门上**
# (像服务器上的标签),屏风那块由 seat_item 跳过不画。

# 一层的厚度 / 层间距(房间单位)。**层高是被「层上要印得下服务名」倒推的**:
# 柜门在 ISO_FX 面上,那个面的纵轴 1 个单位 = 1 屏幕像素,6pt 的字要 8px,
# 所以一层至少 8.6 个单位高——柜子也因此从 20 长到 34(三层就占 30)。
SLOT_H, SLOT_GAP = 8.6, 1.4
SLOT_Z0 = 2.0                   # 最下面那层离柜底多高
# **不再留空槽**:层高撑到 8.6 之后,多一层空的就要再高 10 个单位,柜子会比
# 显示器还高一截,反客为主。
BLANK_SLOTS = 0

# 沿板方向 1 个房间单位 = 2.2361px(横 2、竖 1)。两行字各有各的地盘:
LABEL_LEN = (RX - 3.0) * 2.2361     # 柜顶那张标签(工位名)
SLOT_LEN = (RX - 4.0 - 1.6) * 2.2361    # 层上那行服务名:右端到灯为止
#   ↑ 灯在房间 x = RX-4,名字从 x+1.6 起;沿板方向 1 单位 = 2.2361px

FONT_LABEL = QFont()                # 模块级:paint 每帧重建 QFont 要走字体匹配查找
FONT_LABEL.setPointSize(7)
FONT_LABEL.setBold(True)
FONT_SLOT = QFont()                 # 层上的服务名:比标签再小一档才塞得进
FONT_SLOT.setPointSize(6)
FONT_SLOT.setBold(True)

STATE_TEXT = {UP: "运行中", DOWN: "没在跑", STUCK: "无响应"}
LED = {UP: LED_UP, DOWN: LED_DOWN, STUCK: LED_STUCK}

# 命中区:上面那几个房间坐标在等距投影下的包围盒(paint 和 hit 必须同源,
# 各写一遍必然漂移——工位那几块命中区同一条规矩)。
def _bbox() -> QRectF:
    xs, ys = [], []
    for x in (RACK_X, RACK_X + RX):
        for y in (RACK_Y, RACK_Y + RY):
            for z in (RACK_Z, RACK_Z + RZ):
                q = _pt(x, y, z)
                xs.append(q.x())
                ys.append(q.y())
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


HIT = _bbox()


def hit_rect() -> QRectF:
    return QRectF(HIT)


def tooltip(services, states: dict) -> str:
    lines = [f"{s.name}  {s.address}  "
             f"{STATE_TEXT.get(states.get(s.name, DOWN), '未知')}"
             for s in services]
    return "机柜\n" + "\n".join(lines) if lines else "机柜(没有服务)"


def report(services, states: dict) -> str:
    """气泡里那句话:全绿报平安,否则**点名**是哪几个不对——
    「有服务挂了」还得再凑近看柜灯,等于白说一句。"""
    if not services:
        return ""
    bad = [f"{s.name} {STATE_TEXT.get(states.get(s.name, DOWN), '')}"
           for s in services if states.get(s.name, DOWN) != UP]
    return "、".join(bad) if bad else f"{len(services)} 个服务都正常"


def all_green(services, states: dict) -> bool:
    return bool(services) and all(states.get(s.name) == UP for s in services)


def any_stuck(services, states: dict) -> bool:
    return any(states.get(s.name) == STUCK for s in services)


def draw(p: QPainter, services, states: dict, blink: bool = True,
         dim: bool = False, label: str = "") -> None:
    """把机柜画在工位的桌面上(调用方负责 save/restore 画笔状态)。

    `label` 是工位名:印在**柜顶**上(屏风上那块名牌被柜子挡死了,见上面的说明)。
    `dim` = 这个工位没上班:柜子跟着整张工位一起灰,别在黑屏空椅子旁边留一台
    绿灯常亮的机器——那读起来像「人没在但服务归它管」,状态和场景就打架了。
    """
    x, y, z = RACK_X, RACK_Y, RACK_Z
    body = mix(RACK, RACK_OFF, 0.75) if dim else RACK
    side = mix(RACK_SIDE, RACK_OFF, 0.75) if dim else RACK_SIDE
    top = mix(RACK_TOP, RACK_OFF, 0.75) if dim else RACK_TOP
    p.setPen(Qt.PenStyle.NoPen)
    # 三个面都要画:少一面就塌成纸片(音响踩过)
    p.setBrush(QBrush(side))        # x=RX 那面:侧板,深一档
    p.drawPolygon(_quad((x + RX, y, z), (x + RX, y + RY, z),
                        (x + RX, y + RY, z + RZ), (x + RX, y, z + RZ)))
    p.setBrush(QBrush(body))        # y=RY 那面:柜门,层和灯都在这儿
    p.drawPolygon(_quad((x, y + RY, z), (x + RX, y + RY, z),
                        (x + RX, y + RY, z + RZ), (x, y + RY, z + RZ)))
    p.setBrush(QBrush(top))
    p.drawPolygon(_quad((x, y, z + RZ), (x + RX, y, z + RZ),
                        (x + RX, y + RY, z + RZ), (x, y + RY, z + RZ)))

    # 柜门开在 **y = RY 那个面**上,也就是 ISO_FX 平面:这个平面的横轴走房间的
    # x、纵轴是屏幕往下。挂错成常 x 的面,整排灯会飞到柜子外面去(踩过)。
    rows = len(services) + BLANK_SLOTS
    slot = mix(RACK_SLOT, RACK_OFF, 0.7) if dim else RACK_SLOT
    for i in range(rows):
        zz = z + SLOT_Z0 + i * (SLOT_H + SLOT_GAP)
        svc = services[rows - 1 - i] if (rows - 1 - i) < len(services) else None
        p.save()                        # ① 横板和灯:画在 ISO_FX 面上,u 是**房间单位**
        _on(p, ISO_FX, x + 1.0, y + RY, zz + SLOT_H)
        p.setBrush(QBrush(slot))
        p.drawRect(QRectF(0, -SLOT_H, RX - 2.0, SLOT_H))
        if svc is not None:
            st = states.get(svc.name, DOWN)
            led = LED_DOWN if dim else LED[st]
            if st == STUCK and not blink and not dim:
                led = mix(led, QColor("#ffffff"), 0.5)      # 异常:半拍一闪
            p.setBrush(QBrush(led))
            p.drawRect(QRectF(RX - 4.0, -SLOT_H / 2 - 1.6, 1.8, 3.2))
        p.restore()
        if svc is None:
            continue
        p.save()                        # ② 服务名:**必须另起一个 ISO_TEXT_FX 块**
        # 直接写在上面那个 ISO_FX 块里,字会被横向拉成两倍宽、糊出柜门(踩过)。
        # 这个面的 u 是**沿板方向的像素**、v 是屏幕往下的像素,和上面那套不通用。
        _on(p, ISO_TEXT_FX, x + 1.6, y + RY, zz + SLOT_H)
        p.setPen(QPen(mix(RACK_NAME, RACK_SLOT, 0.55) if dim else RACK_NAME))
        p.setFont(FONT_SLOT)
        p.drawText(QRectF(0, 0.6, SLOT_LEN, SLOT_H - 1.2),
                   int(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter), svc.name)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)

    if label:
        # 工位名印在**柜顶**上(像机箱上贴的那张标签),不印在柜门上:柜门那一条
        # 的「字高」是拿 z 量的(1 单位 = 1px),7pt 的字要 9 个单位,门上腾不出
        # 这么一条又不吃掉一层槽位;柜顶是块 19×18 的大平面,随便放。
        # **要画在槽位之后**:先画的话会被后面那几条横板盖掉(踩过)。
        p.save()
        _on(p, ISO_TEXT_TOP, x + 2.0, y + 3.0, z + RZ)
        p.setPen(QPen(mix(RACK_NAME, RACK_OFF, 0.6) if dim else RACK_NAME))
        p.setFont(FONT_LABEL)
        p.drawText(QRectF(0, 0, LABEL_LEN, 9),
                   int(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter), label)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
