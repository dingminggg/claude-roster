"""办公室画布的配色。**改颜色只改这一个文件**,别再散回各个图元里。

「白模」风:整个场景近乎全白(桌椅、地面都是浅灰白),**颜色只留给两样**——
亮起来的屏幕(= 运行状态)和坐在椅子上的人(= 成员配色)。这样一眼扫过去,
跳出来的就是「谁在干活、谁是谁」,而不是一堆装饰。

层次从底到顶一层比一层亮:
    画布 CANVAS → 地毯 CARPET → 桌面 DESK_TOP
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# ---------- 画布(地板) ----------
CANVAS = QColor("#f3f2f0")      # 大背景:柔和的白,略带暖,读起来像地面而不是纸
GRID = QColor("#e6e4e1")        # 地砖缝:看得见但不抢戏
TILE_ALT = QColor("#efedea")    # 隔一块深一点,像铺开的方砖(纯网格线太像方格纸)
TILE = 60                       # 地砖边长(px)

# ---------- 阴影(3/4 斜视下立体感的主要来源) ----------
# 影子比线条更能说明「这东西离地有高度」。一律低透明度纯黑,别用带色阴影(浅底上会脏)。
SHADOW = QColor(0, 0, 0, 18)
SHADOW_HARD = QColor(0, 0, 0, 26)

# ---------- 部门地毯 ----------
CARPET = QColor("#e9ecf1")
CARPET_EDGE = QColor("#cfd5de")     # 虚线边
CARPET_LABEL = QColor("#6b7280")    # 部门名
GRIP = QColor("#9aa3b0")            # 右下角拉伸角

# ---------- 家具(白模) ----------
DESK_TOP = QColor("#f1f2f4")        # 桌面
DESK_FRONT = QColor("#e2e4e8")      # 桌子前沿(看得见的板厚)
DESK_LEG = QColor("#dcdee3")
DESK_TOP_OFF = QColor("#ebecee")    # 没人时:再冷一档,和有人的桌子拉开
DESK_FRONT_OFF = QColor("#dedfe2")
CHAIR = QColor("#e8eaee")           # 座垫
CHAIR_DARK = QColor("#d7dae0")      # 椅背 / 气杆
MUG = QColor("#dfe2e7")             # 桌上的杯子

# ---------- 电脑 ----------
BEZEL = QColor("#2b2f36")       # 屏幕边框 / 支架:全白场景里唯一的深色物件
SCREEN_OFF = QColor("#3d434c")  # 没开机的屏

# ---------- 人 ----------
HEAD = QColor("#ffffff")        # 脑袋:白的,emoji 压在上面最清楚
OFF_TINT = QColor("#9aa3b0")    # 没人时用来替换成员配色的灰

# ---------- 文字 ----------
TXT = QColor("#1f2328")         # 主文字(名字)
DIM = QColor("#8b929d")         # 次要文字(会话标题 / 会话下拉行)

# ---------- 内联确认(启动键点开后的 ✓ / ✕) ----------
YES_BG = QColor("#15803d")
YES_FG = QColor("#ffffff")
NO_BG = QColor("#e5e7eb")
NO_FG = QColor("#4b5563")

OFF_OPACITY = 0.92              # 没人的工位:桌子已经冷化了,不用再压太狠


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """把 a 往 b 混 t(0~1)。"""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )
