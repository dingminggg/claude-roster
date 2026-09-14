"""桌上那台小机柜:本地服务(mysql / redis / apache)的状态灯。

**它不是独立图元,是工位上的一样家具**——摆在运维桌上、显示器右边,和音响、杯子、
那叠文件一个级别。曾经是占一整格的落地大机柜(还配了「运维走过去看一眼」的动画),
搬到桌上之后那趟路就没意义了:柜子就在他手边。所以这里只导出**画法和命中区**,
由 `seat_item` 在运维那张工位上调用;状态变了他在工位上冒个气泡说一句。

**一台机柜装下所有服务**,一层 1U = 一个服务(右端一颗灯)。桌面尺寸下**印不下
服务名**了(整台柜子才 9 个房间单位宽),所以哪一层是谁只在悬停提示里说;
柜灯负责「有没有出事」,要看是哪一个就悬停、或者等他冒气泡点名。

状态语义和工位「屏幕色 = 运行状态」完全一致:绿 = 端口听得到、灭 = 没在跑、
琥珀半拍一闪 = 端口在但不搭理你。画面上不写状态文字,文字版在悬停提示里。

**只读**:点它不启停服务(要管理员权限,而且看板上误点一下就把 MySQL 关了)。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter

from ..services import DOWN, STUCK, UP
from .iso import ISO_FX
from .iso import on as _on          # 用工位那套固定原点:柜子就摆在工位的桌面上
from .iso import quad as _quad
from .theme import (
    LED_DOWN, LED_STUCK, LED_UP, RACK, RACK_OFF, RACK_SIDE, RACK_SLOT,
    RACK_TOP, mix,
)

# 桌上那台小机柜的房间尺寸和落点。摆在**显示器右边**(x 大那头)、桌面上(z=26)。
# 尺寸得压得够小:它是桌上的一样东西,大了就又变回落地机柜、把显示器比下去。
RX, RY, RZ = 13.0, 9.0, 22.0
RACK_X, RACK_Y, RACK_Z = 38.0, 3.0, 26.0        # 桌面在 z=26
# 宽度按办公桌的短边(DESK_Y=22)来配:太小就成了个不起眼的小盒子,看不出是机柜。
# 高度会盖到后屏风上那块名牌的左端一点点——运维的名字是固定的 `ops`、又是**右对齐**
# 贴着屏风右端,正好躲开;换个长名字就会被柜子啃掉一截。

SLOT_H, SLOT_GAP = 3.4, 1.2     # 一层的厚度 / 层间距(房间单位)
SLOT_Z0 = 2.5                   # 最下面那层离柜底多高
BLANK_SLOTS = 1                 # 服务之外再留一层空槽:机柜本来就有空位

STATE_TEXT = {UP: "运行中", DOWN: "没在跑", STUCK: "无响应"}
LED = {UP: LED_UP, DOWN: LED_DOWN, STUCK: LED_STUCK}

# 命中区:上面那几个房间坐标在 _pt 投影下的包围盒(paint 和 hit 必须同源,
# 各写一遍必然漂移——工位那三块命中区同一条规矩)。
HIT = QRectF(112, 43, 48, 48)


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
         dim: bool = False) -> None:
    """把机柜画在工位的桌面上(调用方负责 save/restore 画笔状态)。

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
        p.save()
        _on(p, ISO_FX, x + 1.0, y + RY, zz + SLOT_H)
        p.setBrush(QBrush(slot))
        p.drawRect(QRectF(0, -SLOT_H, RX - 2.0, SLOT_H))
        if svc is not None:
            st = states.get(svc.name, DOWN)
            led = LED_DOWN if dim else LED[st]
            if st == STUCK and not blink and not dim:
                led = mix(led, QColor("#ffffff"), 0.5)      # 异常:半拍一闪
            p.setBrush(QBrush(led))
            p.drawRect(QRectF(RX - 4.4, -SLOT_H + 0.7, 1.8, SLOT_H - 1.4))
        p.restore()
