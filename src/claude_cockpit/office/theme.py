"""办公室画布的配色。**改颜色只改这一个文件**,别再散回各个图元里。

浅色主题:大背景是柔和的白(不是纯白,纯白刺眼且和白色工牌分不开层),
所有前景色按「在浅底上要看得清」挑,不是把深色主题反一下就完事。

层次是刻意排的,从底到顶一层比一层亮:
    画布 CANVAS → 地毯 CARPET → 工位地面 FLOOR → 桌板 DESK → 工牌/纸面
这样即使不画边框,东西也能靠明度分开。
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# ---------- 画布 ----------
CANVAS = QColor("#f4f5f7")      # 大背景:柔和的白,略带灰
GRID = QColor("#e7e9ee")        # 背景网格:看得见但不抢戏

# ---------- 部门地毯 ----------
CARPET = QColor("#e9ecf1")
CARPET_EDGE = QColor("#cfd5de")     # 虚线边
CARPET_LABEL = QColor("#6b7280")    # 部门名
GRIP = QColor("#9aa3b0")            # 右下角拉伸角

# ---------- 工位 ----------
FLOOR = QColor("#fbfcfd")       # 工位地面:比地毯亮一档,压出「这是一个格子」
FLOOR_HOVER = QColor("#ffffff")
PART = QColor("#dbe0e8")        # 隔断板
PART_TOP = QColor("#eef1f5")    # 隔断顶面(受光面,亮一档做厚度)
DESK = QColor("#d9bd94")        # 桌板:浅木色
DESK_EDGE = QColor("#c3a375")   # 桌板底边(厚度)
DESK_OFF = QColor("#dcd8d1")    # 没人时的桌板:抽掉木色的暖调,一眼看出这位没上班
DESK_EDGE_OFF = QColor("#c8c3ba")
GEAR = QColor("#3b424c")        # 显示器背壳 / 支架:浅底上要够深才看得出是设备
KEYS = QColor("#4a515b")        # 键盘
MOUSE = QColor("#5b636e")
CHAIR = QColor("#aab3c0")       # 扶手
CHAIR_SEAT = QColor("#c3cbd6")  # 坐垫
HEAD = QColor("#ffffff")        # 头顶底盘:白的,emoji 压在上面最清楚
PLANT_POT = QColor("#b99a76")
PLANT = QColor("#5aa36e")
PLANT_OFF = QColor("#b7c2b8")

# ---------- 工牌 ----------
BADGE = QColor("#ffffff")
BADGE_OFF = QColor("#eef0f3")
BADGE_EDGE = QColor("#d3d8e0")  # 白工牌压在浅工位上,得有一条边才立得住
BADGE_TXT = QColor("#1f2328")

# ---------- 文字 ----------
TXT = QColor("#1f2328")         # 主文字
DIM = QColor("#7b8290")         # 次要文字(会话标题 / 会话下拉行)

# ---------- 内联确认(启动键点开后的 ✓ / ✕) ----------
YES_BG = QColor("#15803d")
YES_FG = QColor("#ffffff")
NO_BG = QColor("#e5e7eb")
NO_FG = QColor("#4b5563")

# ---------- 未运行 ----------
# 不再靠整体降透明度(浅底上一降就糊成一片、还看不清),改成明确的灰化配色
OFF_TINT = QColor("#9aa3b0")    # 未运行时替换成员配色的那个灰
OFF_OPACITY = 0.85              # 桌板/绿植已经灰化了,不用再压太狠(压狠了字看不清)


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """把 a 往 b 混 t(0~1)。用来给工位地面上一层状态色的淡淡染色。"""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )
