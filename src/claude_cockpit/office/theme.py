"""办公室画布的配色。**改颜色只改这一个文件**,别再散回各个图元里。

**家具用低饱和的木色和石板色**(浅木桌 + 深灰蓝椅),地面和地毯仍是浅灰白。
之前家具也是近乎全白,结果椅子 `#e8eaee` 和地毯 `#e9ecf1` 几乎同一个明度——
字面意义上消失在地毯里,整个工位读起来是「一团浅灰 + 一块彩色屏幕在飘」。

**饱和色仍然只给两样**:亮起来的屏幕(= 运行状态)和小人(= 成员配色)。家具是
低饱和土色,和状态色(蓝/绿/琥珀)不在同一个饱和度档上,所以不抢戏——一眼扫过去
跳出来的还是「谁在干活、谁是谁」。

对比度是**对着地毯**调的,不是对着画布:工位坐在地毯上,和地毯分不开就白搭。
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

# ---------- 家具 ----------
# 桌子:浅木。三档明度分出「桌面 / 板厚 / 桌腿」,不然等距的盒子看不出是个盒子。
DESK_TOP = QColor("#e6cba6")        # 桌面
DESK_FRONT = QColor("#d2b184")      # 桌子前沿(看得见的板厚)
DESK_LEG = QColor("#c39f71")
DESK_SHADE = QColor("#b18a5c")      # 桌子底下背光的板面(侧板腿 / 抽屉柜)
DRAWER_LINE = QColor("#94713f")     # 抽屉缝
# 工位后面那道低屏风(灰蓝布)。**这是「工位 vs 餐桌」最强的信号**——
# 光是一块板 + 四条细腿,画出来就是张餐桌。
PARTITION = QColor("#bac2d0")
PARTITION_TOP = QColor("#dae0e8")
DESK_TOP_OFF = QColor("#dcd7d0")    # 没人时:抽掉木色的暖,褪成灰木
DESK_FRONT_OFF = QColor("#c8c2ba")
# 椅子:深灰蓝(参考图那把转椅)。比显示器边框浅一档——屏幕边框得是全场最深的。
CHAIR = QColor("#6f7b8d")           # 座垫 / 椅背中间那块软垫
CHAIR_DARK = QColor("#57616f")      # 椅背
CHAIR_LEG = QColor("#8d97a5")       # 五爪底盘:比椅背浅,压在地毯上才看得见
MUG = QColor("#f4f6f8")             # 桌上的杯子:白瓷,压在木色上才跳
KEYBOARD = QColor("#525b6a")        # 键盘 / 鼠标:深灰,压在木色桌面上才看得见
KEY = QColor("#6f7889")             # 键盘上那几道键位
PAPER = QColor("#fdfdfe")           # 桌上那叠文件(一张 = 一条历史会话)
PAPER_LINE = QColor("#bcc3cf")      # 纸上那两条「字」
PAPER_EDGE = QColor("#c7b393")      # 纸的边:偏木色的暖灰,别用冷灰(压在木桌上会脏)

# ---------- 桌上的小音响 ----------
SPEAKER = QColor("#3b424c")         # 箱体
SPEAKER_CONE = QColor("#6b7480")    # 喇叭单元 / 顶面
SPEAKER_SIDE = QColor("#2f353d")    # 右前那个侧面:比正面深一档,盒子才立得起来
WAVE = QColor("#f59e0b")            # 音浪:琥珀色,和状态色(蓝/绿)不撞

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


# ---------- 机房(本地服务的机柜) ----------
# 机柜是**全场最深的物件**:它不是办公家具,和浅木桌摆在一起才一眼分得出「这是设备」。
RACK = QColor("#3a4049")            # 柜体正面(装着服务名和那排 1U 槽位)
RACK_SIDE = QColor("#2c313a")       # 右前那个侧面:深一档,盒子才立得起来
RACK_TOP = QColor("#4a515c")        # 顶面
RACK_SLOT = QColor("#2a2f37")       # 一个 1U 槽位
RACK_NAME = QColor("#e8ecf2")       # 印在柜面上的服务名(深柜体上只能用浅字)
RACK_OFF = QColor("#9aa1ac")        # 没跑:整柜褪成灰,和空工位一个口径

# 状态灯。绿/琥珀和工位屏幕同一套语义,不另起一套颜色。
LED_UP = QColor("#22c55e")          # 端口听得到
LED_STUCK = QColor("#f0a92e")       # 端口在但不搭理(防火墙吞了 / 进程僵住)
LED_DOWN = QColor("#4b525c")        # 灭灯:比柜体浅一点点,看得出「有这个灯,只是没亮」
