"""一个工位 = 一个成员的控制台。**等距(isometric)**画法,镜头在右前方高处:

    名字 → 桌子(菱形桌面 + 两条前沿板厚 + 四条竖腿)→ 桌上的显示器/音响/杯子/文件
         → 椅子和人(在桌子左前方,面朝桌子,所以看到的是后脑勺和椅背)

所有家具都摆在一套房间坐标里(见 _pt / _on),投影出来自然是同一个朝向——之前每个
图元各画各的角度,凑出来是张「立面图」,看着生硬。**颜色只给两样**:屏幕(=运行
状态)和人(=成员配色),其余全是白模,场景才不花。没上班就是**空椅子 + 黑屏**。

**工位上没有任何按钮**:启动、选会话、复制地址那些全在右键菜单里(见 view.py)。
工位本身只有两件事——左键点它把控制台弹到眼前,拖它换位置。

本图元只画和报事件:状态由 set_* 喂进来,不认识 peers / winman / launcher。
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF, QTransform,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ..layout import SEAT_H, SEAT_W
from . import bubble, person, rack_item
from .iso import (
    DESK_X, DESK_Y, ISO_FX, ISO_FY, ISO_TEXT_FX, ISO_TEXT_TOP, ISO_TOP,
)
from .iso import on as _on
from .iso import pt as _pt
from .iso import quad as _quad
from .theme import (
    BEZEL, CHAIR, CHAIR_DARK, DESK_FRONT, DESK_FRONT_OFF, DESK_LEG, DESK_TOP,
    CHAIR_LEG, DESK_SHADE, DESK_TOP_OFF, DIM, DRAWER_LINE, KEY, KEYBOARD, MUG, NO_BG, NO_FG,
    OFF_OPACITY, PARTITION, PARTITION_TOP, SCREEN_OFF,
    PAPER, PAPER_EDGE, PAPER_LINE, SHADOW, SPEAKER, SPEAKER_CONE, SPEAKER_SIDE, WAVE, SHADOW_HARD, TXT, YES_BG,
    YES_FG, mix,
)


def _font(size: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f


# 字号从不随状态变:提到模块级建一次。paint 每帧重建 QFont 要走字体匹配查找,
# 而 paint 是「每个工位 × 每次 tick/闪烁/悬停」都跑的。
FONT_NAME = _font(8, bold=True)     # 挡板上那块名牌
FONT_SUB = _font(8)                 # 会话行 / 控制台标题
FONT_PAPER = _font(6, bold=True)    # 纸上那个 issue 号


# 屏幕上那几行「字」:忙的时候往上滚,像终端在刷输出。
# 宽度表按成员名错开一个起点,免得一屋子屏幕整齐划一地同步滚(那看着像动画贴图)。
SCREEN_LINES = (15, 9, 16, 12, 19, 8, 14, 10)
LINE_GAP = 4.0                      # 行距(房间单位)
SCROLL_STEP = 0.55                  # 每帧往上挪多少

# 桌上那叠文件:一张纸 = 一条历史会话,最上面那张印着 issue 号。
# **尺寸是被「放得下 6 位数字」倒推出来的**:纸上那行字走 ISO_TEXT_TOP,
# 沿纸的 x 方向 1 个房间单位 = 2.2361px(横 2、竖 1),6 位数字(6pt)在真机上
# 要 30px,加两边留白 → 纸至少 16 个单位长,取 17。
# **别拿 QFontMetrics 去卡这条**:离屏平台的回退字体比真机宽一大截(同一串数字
# 48px vs 30px),按它算会把纸撑到桌子那么大——用例卡的是几何预算 PAPER_LEN。它同时也是右键「接着这条继续 / 删除这条记录」的唯一
# 入口,画小了点不着。
PAPER_X, PAPER_Y = 38.0, 4.0            # 最下面那张纸的落点(显示器右边)
PAPER_W, PAPER_H = 17.0, 15.0           # 一张纸多大(房间单位)
PAPER_LEN = PAPER_W * 2.2361            # 纸上那行字的可用长度(px)
# 一叠里每张错开多少。纸放大之后 0.6 个单位看不出是「一叠」,得跟着纸一起放大。
PAPER_STEP = 1.4

# 「起来了」的状态:明暗、手型、屏幕闪统一按它判断,别散着写 == "running"
UP_STATES = ("running", "busy", "idle")



@dataclass(frozen=True)
class _Style:
    label: str      # 只出现在 tooltip 里(画面上不写状态文字)
    glow: str       # 屏幕颜色 —— 这才是状态的表达方式


STATE_STYLE = {
    "down":      _Style("未上班", "#c9ced6"),
    "launching": _Style("启动中", "#f0a92e"),
    "busy":      _Style("忙碌中", "#3b82f6"),
    "idle":      _Style("空闲",   "#22c55e"),
    "running":   _Style("运行中", "#22c55e"),
}


# 显示器在桌上的位置和宽度(房间单位)。名牌的左边界由它算出来,所以显示器一动、
# 名牌跟着动,不用手调两处。
MON_X, MON_W, MON_H = 12.0, 24.0, 28.0
MON_Y = 8.0                                     # 显示器摆在桌上的进深位置

# 屏风上那块名牌:从显示器右沿起、到桌子右端止。
# 名牌在 y=1.4 的屏风面上、显示器在 y=MON_Y 的面上,两个面差 (MON_Y-1.4) 个单位才
# 对齐到同一条屏幕竖线上(屏幕 x = OX + (x房间 - y房间)*2),所以要减掉,不是直接接上。
# 4.6 那个数是 MON_Y - 1.4(显示器面和屏风面的进深差),显示器一挪就得跟着变,
# 所以这里直接用 MON_Y 算,别再写死。
PLATE_X = MON_X + MON_W - (MON_Y - 1.4) + 0.3   # 再留 0.3 单位的缝
# 长度是**沿板子方向的真实长度**、不是横向投影宽度:横向差 1 单位 = 2px,
# 沿板方向就是 2/0.8944 = 2.2361px。桌子或显示器改了,这里自动跟着变。
PLATE_LEN = (DESK_X - PLATE_X) * 2.2361


_PLATE_FM: QFontMetricsF | None = None


def _plate_text(name: str) -> str:
    """按**字宽**把名字裁到屏风上那块名牌装得下——名牌只有 PLATE_LEN 那么长,
    按字数裁不行:`etl` 和 `customer-web` 同样是 3/12 个字符,宽度差三倍。"""
    global _PLATE_FM
    if _PLATE_FM is None:                   # QFontMetricsF 得等 QApplication 起来才能建
        _PLATE_FM = QFontMetricsF(FONT_NAME)
    return _PLATE_FM.elidedText(name, Qt.TextElideMode.ElideRight, PLATE_LEN)


class SeatItem(QGraphicsObject):
    """一个工位。QGraphicsObject(而非 QGraphicsItem)是为了能发信号。"""

    clicked = Signal(str)               # 点工位:置前该成员的控制台
    speaker_clicked = Signal(str)       # 点 🔊:停止朗读
    moved = Signal(str)                 # 拖完:该存盘了

    # 椅子中心(房间坐标)。paint 和命中区都从这里取,别各写一份。
    HX, HY = 19.0, 27.0

    def __init__(self, member):
        super().__init__()
        self.name = member.name
        self.color = QColor(member.color)
        self._state = "down"
        self._msg = False
        self._blink = True
        self._speaking = False
        self._away = False      # 跑腿送信去了:椅子空着,人在画布上走
        self._title = ""
        self._sub = "新会话"
        self._papers = 0                # 桌上那叠文件的张数 = 历史会话条数
        self._papers_on = True          # 这个工位有没有文件堆(运维那张没有)
        self._tag = ""                  # 最上面那张纸上印的 issue 号(认不出就留白)
        self._wave = 0                  # 音浪动画的相位(朗读时才转)
        self._scroll = 0.0              # 屏幕滚动的偏移(忙的时候才转)
        k = sum(ord(c) for c in self.name) % len(SCREEN_LINES)
        self._lines = SCREEN_LINES[k:] + SCREEN_LINES[:k]
        self._hover = False
        # 桌上那台小机柜:只有运维那张工位有(`view` 给它喂服务清单)。
        self._services: list = []
        self._svc_states: dict[str, str] = {}
        self._say: list[str] = []           # 正在说的那句话(折好行的)
        self._say_timer = QTimer(self)      # 自带表:说完自己收回去
        self._say_timer.setSingleShot(True)
        self._say_timer.timeout.connect(lambda: self.say(""))
        self._press_pos = None          # 按下时的位置,用来判断松手时是否真挪过
        # 只要可拖,**不要 ItemIsSelectable**:Qt 拖一个图元时会把所有「选中的」
        # 可移动图元一起拖走。工位可选的话,点过它之后再拖地毯,它会既作为子项
        # 跟着父级走一次、又作为选中项被拖一次,比别人多挪一倍(踩过)。
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setAcceptHoverEvents(True)

    # ---------- 状态入口(由 OfficeWindow 转发 main 的 tick) ----------
    def set_run_state(self, state: str) -> None:
        self._state = state if state in STATE_STYLE else "running"
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.is_up()
                       else Qt.CursorShape.ArrowCursor)
        self._sync_tip()
        self.update()

    # ---------- 桌上的机柜(只有运维那张工位有) ----------
    def set_services(self, svcs) -> None:
        self._services = list(svcs)
        self._sync_tip()
        self.update()

    def set_service_states(self, states: dict) -> None:
        for name, st in (states or {}).items():
            self._svc_states[name] = st
        self._sync_tip()
        self.update()

    def has_rack(self) -> bool:
        return bool(self._services)

    def has_papers(self) -> bool:
        return self._papers_on and bool(self._papers)

    def service_report(self) -> str:
        return rack_item.report(self._services, self._svc_states)

    def rack_all_green(self) -> bool:
        return rack_item.all_green(self._services, self._svc_states)

    def say(self, text: str, ms: int = 0) -> None:
        """在工位上冒个气泡说一句(`text` 为空 = 收回气泡)。

        **停多久按字数算**——一句「都正常」和一段点名三个服务的话,给同样的时间
        要么干等、要么根本没读完(同送信小人那条)。
        """
        self.prepareGeometryChange()        # 气泡比工位框高,包围盒要跟着变
        self._say = bubble.wrap(text)
        self._say_timer.stop()
        if self._say:
            self._say_timer.start(ms or min(6000, 1600 + len(text) * 90))
        self.update()

    def is_saying(self) -> bool:
        return bool(self._say)

    def set_message(self, on: bool) -> None:
        self._msg = bool(on)
        self.update()

    def set_blink(self, on: bool) -> None:
        self._blink = bool(on)
        if (self.is_flashing() or self._msg
                or rack_item.any_stuck(self._services, self._svc_states)):
            self.update()

    def set_away(self, on: bool) -> None:
        """离座(跑腿送信中):画成空椅子。不然工位上坐着一个、画布上还走着一个,
        同一个人出现两次。"""
        if self._away != bool(on):
            self._away = bool(on)
            self.update()

    def set_speaking(self, on: bool) -> None:
        if self._speaking != bool(on):
            self._speaking = bool(on)
            self._wave = 0
            self.update()

    def is_working(self) -> bool:
        """屏幕在滚 = **正在干活**。空闲的不滚:一屋子屏幕全在动就没有信息量了,
        而且那是「谁在忙」的第二遍表达(第一遍是屏幕颜色),动起来才互相加强。"""
        return self._state == "busy"

    def advance_scroll(self) -> None:
        """屏幕往上滚一帧(由 OfficeWindow 的定时器驱动,只在有人忙时才转)。"""
        if self.is_working():
            self._scroll = (self._scroll + SCROLL_STEP) % (len(self._lines) * LINE_GAP)
            self.update()

    def advance_wave(self) -> None:
        """音浪往前走一帧(由 OfficeWindow 的定时器驱动,只在朗读时转)。"""
        if self._speaking and self.is_up():
            self._wave = (self._wave + 1) % 3
            self.update()

    def set_title(self, text: str) -> None:
        self._title = text or ""
        self._sync_tip()
        self.update()

    def set_session_count(self, n: int) -> None:
        """桌上那叠文件 = 这个成员的历史会话。右键点它出会话列表。"""
        n = max(0, int(n))
        if n != self._papers:
            self._papers = n
            self.update()

    def set_papers_enabled(self, on: bool) -> None:
        """这个工位显不显示文件堆。

        **运维那张关掉**:那叠纸的意思是「这个员工有几条历史会话、右键挑一条接着
        聊」,运维不走这条路——他桌上的活儿是那台机柜。关掉之后「显示器右边」那块
        地也就腾给机柜了,两样不会挤在一起。
        """
        if self._papers_on != bool(on):
            self._papers_on = bool(on)
            self.update()

    def set_session_tag(self, tag: str) -> None:
        """最上面那张纸上印的 issue 号(由 `sessions.issue_tag` 从会话标题里抠)。"""
        tag = str(tag or "")[:6]
        if tag != self._tag:
            self._tag = tag
            self.update()

    def set_subtitle(self, text: str) -> None:
        """没上班时那条「上次会话 / 新会话」——只出现在文件堆的悬停提示里。"""
        self._sub = text or "新会话"
        self._sync_tip()
        self.update()

    def _sync_tip(self, where: str = "seat") -> None:
        """悬停提示按落点给不同的信息:画面上不写状态和会话标题(那会把白模
        场景堆满字),但悬停要查得到——鼠标停在人身上问「他在干嘛」,
        停在文件堆上问「这是哪条会话」。"""
        if where == "rack":
            tip = rack_item.tooltip(self._services, self._svc_states)
        elif where == "person":
            tip = f"{self.name} · {self.status_text()}"
        elif where == "files":
            n = self._papers
            tip = f"{self._title or self._sub}" + (f"(共 {n} 条历史会话)" if n else "")
        else:
            tip = f"{self.name} · {self.status_text()}"
            if self._title:
                tip += "\n" + self._title
        self.setToolTip(tip)

    # ---------- 查询(测试与绘制共用) ----------
    def is_up(self) -> bool:
        return self._state in UP_STATES

    def status_text(self) -> str:
        return STATE_STYLE[self._state].label

    def is_flashing(self) -> bool:
        return self.is_up() and self._msg and self._blink

    # ---------- 命中区 ----------
    def boundingRect(self) -> QRectF:
        """工位框;正在说话时往上让出气泡那一块(不让的话气泡会被裁掉半截)。"""
        r = QRectF(0, 0, SEAT_W, SEAT_H)
        if self._say:
            r.setTop(-bubble.height(self._say) - 6)
        return r

    # 三块命中区的数值 = 对应家具在 _pt 投影下的包围盒。改了家具的房间坐标,
    # 这里必须跟着改——paint 和 hit 对不上,就会「点纸弹控制台」。三块互不重叠。
    def r_speaker(self) -> QRectF:
        """桌上那个小音响(桌子左角):朗读时它冒音浪,点它停播。"""
        return QRectF(51, 16, 17, 21)

    def r_person(self) -> QRectF:
        """人和椅子那一块:右键它 = 对这个人下命令(上班 / 下班)。"""
        return QRectF(23, 50, 40, 66)

    def r_files(self) -> QRectF:
        """桌上那叠文件:一张纸 = 一条历史会话,右键它挑会话。

        数值 = 那叠纸在 `_pt` 投影下的包围盒(四个角取 min/max),纸一改尺寸这里
        自动跟着变——paint 和 hit 各写一份必然漂移(工位那几块命中区同一条规矩)。
        """
        xs, ys = [], []
        for x, y in ((PAPER_X, PAPER_Y), (PAPER_X + PAPER_W, PAPER_Y),
                     (PAPER_X, PAPER_Y + PAPER_H),
                     (PAPER_X + PAPER_W, PAPER_Y + PAPER_H)):
            for z in (26.3, 28.5):
                q = _pt(x, y, z)
                xs.append(q.x())
                ys.append(q.y())
        return QRectF(min(xs) - 2, min(ys) - 2,
                      max(xs) - min(xs) + 4, max(ys) - min(ys) + 4)

    def r_rack(self) -> QRectF:
        """桌上那台小机柜(只有运维那张工位有):右键它复制服务地址。"""
        return rack_item.hit_rect()

    def hit(self, pos: QPointF) -> str:
        """局部坐标 → "speaker" / "person" / "files" / "seat"。

        分区是有语义的:点人 = 管他上下班,点文件 = 管他的会话历史。
        paint 和这里共用同一份 r_*,两处各写一遍必然漂移。
        """
        if self.is_up() and self._speaking and self.r_speaker().contains(pos):
            return "speaker"
        if self.r_person().contains(pos):
            return "person"
        if self._services and self.r_rack().contains(pos):
            return "rack"
        if self.has_papers() and self.r_files().contains(pos):
            return "files"
        return "seat"

    # ---------- 小人 ----------
    def chair_pos(self) -> QPointF:
        """椅子在地面上的落点(工位局部坐标)。walker 从这儿出发、也走到这儿。"""
        return _pt(self.HX, self.HY, 0)

    def _person_sitting(self, p: QPainter) -> None:
        """坐姿(画法见 office/person.py,和送信的小人共用一份)。

        **底盘和气杆在 (HX, HY),人和椅背往 +y 偏一点**:人面朝 -y(显示器那边),
        背靠的椅背自然在 +y 那侧;等距下 +y = 屏幕左下,椅背落在人的左下方,一眼能
        看出这把椅子是**朝着屏幕**的。偏太多人就不在座位中间了(踩过),所以只偏
        1.5 / 4 个单位——够看出朝向,又还坐在底盘正上方。
        谁压住谁靠画序决定(椅背在人之后画),不靠 y。
        """
        person.draw_sitting(p, self.color, self.HX, self.HY + 1.5)

    # ---------- 绘制 ----------
    def paint(self, p: QPainter, opt, widget) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        up = self.is_up()
        # present ≠ up:`启动中` 是「人到了但还没坐下」——屏幕该亮琥珀、椅子旁该站着人,
        # 只有真的没上班(down)才是空椅子 + 黑屏 + 整张置灰。而 up 仍然只管「起来了」
        # 那几个状态(闪烁、朗读、点击置前都按它判断,别混用)。
        present = self._state != "down"
        st = STATE_STYLE[self._state]
        p.setOpacity(1.0 if present else OFF_OPACITY)
        flash = self.is_flashing()
        glow = QColor(st.glow)
        p.setPen(Qt.PenStyle.NoPen)

        # 有新消息:**只闪屏幕**,不罩整张工位。整张闪太吵——一屋子人里有两三个在
        # 等你,画面就有两三大块在呼吸;屏幕本来就是这张图上唯一的亮色块,闪它已经
        # 够跳了,而且「状态」和「在等你」都落在同一个物件上,不打架。
        screen_col = SCREEN_OFF
        if present:
            screen_col = mix(glow, QColor("#ffffff"), 0.5) if flash else glow
        if self._hover:
            p.setBrush(QBrush(QColor(255, 255, 255, 170)))
            p.drawRoundedRect(QRectF(6, 10, SEAT_W - 12, SEAT_H - 16), 14, 14)

        # ============ 家具(全部走等距投影,见 _pt / _on) ============
        # 桌子:DESK_X × DESK_Y 的长方桌(长边对着人),桌面在 z=26。
        # 先画影子和桌腿,再用桌面盖住腿的上半截。
        p.setBrush(QBrush(SHADOW))
        p.drawPolygon(_quad((2, 2, 0), (DESK_X - 1, 2, 0),
                            (DESK_X - 1, DESK_Y - 2, 0), (2, DESK_Y - 2, 0)))
        # 桌子底下:**左端侧板腿 + 右端抽屉柜**,中间整段留空。四条细腿 + 底下全空
        # 那是餐桌,工位的辨识度就在这两块板和后面那道屏风上。
        # (曾经沿着近侧长边加过一条通长挡板,撤了:只撤座位那一段更尴尬,整条去掉才干净。)
        # 按 x+y(离镜头远近)排画序,不然会穿帮。
        shade = DESK_SHADE if present else DESK_FRONT_OFF
        p.setBrush(QBrush(shade))
        p.save()                                    # 左侧板腿(看到的是它朝右的那面)
        _on(p, ISO_FY, 3, 3, 23)
        p.drawRect(QRectF(0, 0, 16, 23))
        p.restore()
        p.save()                                    # 抽屉柜:右侧面
        _on(p, ISO_FY, DESK_X - 2, 3, 23)
        p.drawRect(QRectF(0, 0, 16, 23))
        p.restore()
        p.save()                                    # 抽屉柜:正面 + 三道抽屉缝
        _on(p, ISO_FX, DESK_X - 13, 19, 23)
        p.drawRect(QRectF(0, 0, 10, 23))
        p.setBrush(QBrush(DRAWER_LINE if present else DESK_TOP_OFF))
        for i in range(3):
            p.drawRect(QRectF(1.5, 4 + i * 6.5, 7, 0.8))
        p.restore()
        p.save()                                    # 桌面(水平面)
        _on(p, ISO_TOP, 0, 0, 26)
        p.setBrush(QBrush(DESK_TOP if present else DESK_TOP_OFF))
        p.drawRoundedRect(QRectF(0, 0, DESK_X, DESK_Y), 1.2, 1.2)
        p.restore()
        p.setBrush(QBrush(DESK_FRONT if present else DESK_FRONT_OFF))
        p.save()                                    # 两条**朝着我们**的桌沿板厚
        _on(p, ISO_FX, 0, DESK_Y, 26)
        p.drawRect(QRectF(0, 0, DESK_X, 3))
        p.restore()
        p.save()
        _on(p, ISO_FY, DESK_X, 0, 26)
        p.drawRect(QRectF(0, 0, DESK_Y, 3))
        p.restore()

        # 后屏风:立在桌子里侧边上,比桌面高出 12。整个场景里「这是工位不是餐桌」
        # 就靠它一眼定性。画在桌面之后、桌上东西之前(它是最远的那一样)。
        p.save()
        _on(p, ISO_TOP, 0, 0, 41)
        p.setBrush(QBrush(PARTITION_TOP))
        p.drawRect(QRectF(0, 0, DESK_X, 1.4))       # 顶沿
        p.restore()
        p.save()
        _on(p, ISO_FX, 0, 1.4, 41)
        p.setBrush(QBrush(PARTITION))
        p.drawRect(QRectF(0, 0, DESK_X, 15))        # 朝我们那面
        p.restore()
        # 成员名:印在屏风**右段**(显示器右边那截空出来的地方)。
        # 用 ISO_TEXT_FX 而不是 ISO_FX——后者会把字横向拉成两倍宽。
        p.save()
        _on(p, ISO_TEXT_FX, PLATE_X, 1.4, 41)
        p.setFont(FONT_NAME)
        p.setPen(QPen(TXT if present else DIM))
        p.drawText(QRectF(0, 0, PLATE_LEN, 12),                  # 右对齐:贴屏风右端,
                   Qt.AlignmentFlag.AlignRight                   # 别顶着显示器那头
                   | Qt.AlignmentFlag.AlignVCenter, _plate_text(self.name))
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)

        # 显示器:立在桌子里侧(y 小),**屏幕朝左前**,正对着坐在那边的人
        p.save()
        _on(p, ISO_FX, MON_X, MON_Y, 29 + MON_H)    # 底边压在支架上(z=29)
        p.setBrush(QBrush(BEZEL))
        p.drawRoundedRect(QRectF(0, 0, MON_W, MON_H), 1.5, 1.5)
        p.setBrush(QBrush(screen_col))
        p.drawRoundedRect(QRectF(1, 1.2, MON_W - 2, MON_H - 3.6), 1, 1)
        if present:
            p.setBrush(QBrush(QColor(255, 255, 255, 145)))
            p.save()
            # 裁到屏幕面上:滚出上沿的那行得切掉,不然会画到边框和桌面上去。
            # (裁剪跟着当前变换走,所以这里裁出来的是个平行四边形,正好贴合屏幕。)
            p.setClipRect(QRectF(1, 1.2, MON_W - 2, MON_H - 3.6))
            span = len(self._lines) * LINE_GAP
            for i, wu in enumerate(self._lines):
                y = 2.4 + i * LINE_GAP - self._scroll
                if y < 1.2 - LINE_GAP:      # 滚到上面去了 → 从底下再进来
                    y += span
                p.drawRect(QRectF(2.6, y, wu, 1.4))
            p.restore()
        p.restore()
        p.setBrush(QBrush(BEZEL))                   # 支架 + 底座
        stand = _pt(MON_X + MON_W / 2, MON_Y, 29)
        p.drawRect(QRectF(stand.x() - 2.5, stand.y(), 5, 3))
        p.save()
        _on(p, ISO_TOP, MON_X + MON_W / 2 - 3, MON_Y - 2.5, 26.4)
        p.drawRoundedRect(QRectF(0, 0, 6, 5), 1.2, 1.2)
        p.restore()

        # 键盘 + 鼠标:摆在显示器**前面**(y 大 = 离人近),正好是坐着那人手的位置
        p.save()
        _on(p, ISO_TOP, 16, 13, 26.3)
        p.setBrush(QBrush(KEYBOARD))
        p.drawRoundedRect(QRectF(0, 0, 15, 5), 1, 1)
        p.setBrush(QBrush(KEY))                     # 三道键位,不然只是块深色板子
        for i in range(3):
            p.drawRect(QRectF(1, 1 + i * 1.3, 13, 0.6))
        p.restore()
        p.save()                                    # 键盘前沿的厚度
        _on(p, ISO_FX, 16, 18, 26.3)
        p.setBrush(QBrush(KEYBOARD))
        p.drawRect(QRectF(0, 0, 15, 1.2))
        p.restore()
        p.save()
        _on(p, ISO_TOP, 31, 15, 26.3)
        p.setBrush(QBrush(KEYBOARD))
        p.drawRoundedRect(QRectF(0, 0, 3, 4.2), 1.4, 1.4)   # 鼠标
        p.restore()

        # 桌上的小音响(桌子后左角)。**别摆在人正前方**:小人的头会顶到桌面上来,
        # 摆在那儿就压在脑袋上,连命中区都和「点人」抢(踩过)。
        p.save()
        _on(p, ISO_TOP, 1, 2, 38)
        p.setBrush(QBrush(SPEAKER_CONE))
        p.drawRoundedRect(QRectF(0, 0, 3.5, 4), 0.8, 0.8)   # 顶面
        p.restore()
        p.save()
        _on(p, ISO_FY, 4.5, 2, 38)
        p.setBrush(QBrush(SPEAKER_SIDE))
        p.drawRect(QRectF(0, 0, 4, 12))                 # 右前那个侧面
        p.restore()                                     # (等距下一个盒子该露三面:
        p.save()                                        #  顶 + 左前 + 右前,少一面就塌)
        _on(p, ISO_FX, 1, 6, 38)
        p.setBrush(QBrush(SPEAKER))
        p.drawRect(QRectF(0, 0, 3.5, 12))               # 朝左前的正面
        p.setBrush(QBrush(SPEAKER_CONE))
        p.drawEllipse(QRectF(0.8, 5, 2, 3.2))           # 低音单元
        p.drawEllipse(QRectF(1.3, 1.8, 1.1, 1.7))       # 高音单元
        p.restore()
        if up and self._speaking:
            # 音浪:从音响往左右两侧一圈圈扩散,越远越淡(比竖条音量表更像声音)
            c0 = _pt(2.75, 4, 32)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(3):
                r = 10 + i * 7 + self._wave * 2         # 相位推着往外走
                c = QColor(WAVE)
                c.setAlpha(max(0, 190 - i * 55 - self._wave * 20))
                p.setPen(QPen(c, 1.8))
                box = QRectF(c0.x() - r, c0.y() - r * 0.5, r * 2, r)
                p.drawArc(box, -50 * 16, 100 * 16)
                p.drawArc(box, 130 * 16, 100 * 16)
            p.setPen(Qt.PenStyle.NoPen)

        # 杯子:就在音响**前面**。要读成「前面」得 x 和 y 一起加——等距下只加 y 是
        # 往左前走,看着像「在音响左边」;x、y 同时加才是屏幕上的正下方。
        p.setBrush(QBrush(MUG))
        top = _pt(10.5, 11.5, 32)
        p.drawRect(QRectF(top.x() - 4.5, top.y(), 9, 6))
        p.drawEllipse(QRectF(top.x() - 4.5, top.y() + 3.5, 9, 4.5))
        p.drawEllipse(QRectF(top.x() - 4.5, top.y() - 2.2, 9, 4.5))

        # 桌上一叠文件:一张纸 = 一条历史会话,最上面那张印着 issue 号。
        # 摆在**显示器右侧**(x 大)。**别画小**:这块是右键「接着这条继续 /
        # 删除这条记录」的唯一入口,小了点不着(命中区 r_files 直接按这里的
        # 尺寸算出来)。运维那张工位没有这叠纸(见 set_papers_enabled),
        # 那块地让给了桌上的机柜。
        if self.has_papers():
            n = min(3, self._papers)
            for i in range(n):
                p.save()
                _on(p, ISO_TOP, PAPER_X - i * PAPER_STEP,
                    PAPER_Y - i * PAPER_STEP, 26.3 + i * 0.9)
                p.setPen(QPen(PAPER_EDGE, 0.6))     # 白纸压木桌,勾条暖灰边才有厚度
                p.setBrush(QBrush(PAPER))
                p.drawRoundedRect(QRectF(0, 0, PAPER_W, PAPER_H), 0.9, 0.9)
                p.restore()
            p.save()                        # 最上面那张:印 issue 号,没有就两条「字」
            top_x = PAPER_X - (n - 1) * PAPER_STEP
            top_y = PAPER_Y - (n - 1) * PAPER_STEP
            top_z = 26.3 + (n - 1) * 0.9
            if self._tag:
                # 走 ISO_TEXT_TOP:直接用 ISO_TOP 会把字横竖都拉成 2.236 倍
                _on(p, ISO_TEXT_TOP, top_x + 1.6, top_y + 3.0, top_z)
                p.setPen(QPen(TXT if present else DIM))
                p.setFont(FONT_PAPER)
                p.drawText(QRectF(0, 0, PAPER_LEN - 6, 9),
                           int(Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter), self._tag)
            else:
                _on(p, ISO_TOP, top_x, top_y, top_z)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(PAPER_LINE))
                p.drawRect(QRectF(2.5, 4, PAPER_W - 6, 1.0))
                p.drawRect(QRectF(2.5, 7, PAPER_W - 9, 1.0))
            p.restore()
            p.setPen(Qt.PenStyle.NoPen)

        # 桌上那台小机柜(只有运维那张工位有):摆在**显示器右边**。
        # 画在文件堆之后、人之前——它比人离镜头远,画在人后面会被前面的东西盖住。
        if self._services:
            rack_item.draw(p, self._services, self._svc_states,
                           blink=self._blink, dim=not present)

        # ============ 椅子和人 ============
        # 坐在桌子的左前方(y 大 = 离镜头近),面朝桌子,所以我们看到的是后脑勺和椅背。
        # 画序:影子 → 五爪底盘 → 气杆 → 座垫 → 人 → 椅背(椅背离镜头最近,压住身体)。
        if not present:
            p.save()                                # 空工位:椅子淡进地毯,才读得出「没人」
            p.setOpacity(0.5)                       # (深灰蓝不淡的话像「人刚离开」)
        HX, HY = self.HX, self.HY                   # 椅子中心(房间坐标)
        hub = _pt(HX, HY, 0)
        p.setBrush(QBrush(SHADOW))
        p.drawEllipse(QRectF(hub.x() - 23, hub.y() - 11, 46, 22))
        if present:                             # 腿在椅子**之前**画,见 person 里的说明
            person.draw_sitting_legs(p, self.color, HX, HY + 1.5)
        p.setPen(QPen(CHAIR_LEG, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        import math                                 # 五爪:在房间平面上均分五个方向再投影
        feet = [(HX + 7.5 * math.cos(t), HY + 7.5 * math.sin(t))
                for t in (math.radians(-90 + i * 72) for i in range(5))]
        for fx, fy in feet:
            p.drawLine(hub, _pt(fx, fy, 1.5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(CHAIR_LEG))
        for fx, fy in feet:
            c = _pt(fx, fy, 1.5)
            p.drawEllipse(QRectF(c.x() - 2.4, c.y() - 1.6, 4.8, 3.2))
        p.setBrush(QBrush(CHAIR_DARK))              # 气杆
        gas = _pt(HX, HY, 15)
        p.drawRect(QRectF(gas.x() - 2, gas.y(), 4, 13))
        p.save()                                    # 座垫(水平面):从椅背往前伸出来一截
        _on(p, ISO_TOP, HX - 4, HY - 4, 18)
        p.setBrush(QBrush(CHAIR))
        p.drawRoundedRect(QRectF(0, 0, 8, 8), 2, 2)
        p.restore()
        if present and not self._away:              # 坐着的人:椅背会压住他的下半身
            self._person_sitting(p)
        # 椅背:离镜头最近,压住身体。**画在 ISO_FX 面上**——画面里别的东西都是斜的,
        # 椅背要是画成屏幕坐标的矩形(上沿水平),就像一块正对镜头的板子,读不出这把
        # 椅子朝哪边(踩过)。躯干也在同一个面上,两者上沿平行,肩膀才是等宽的一条。
        # 特意矮一档(中背椅):椅背一高就把成员配色全盖住了,只剩个脑袋分不出谁是谁。
        p.save()                                # 椅背在座垫**后沿**(人背后那侧)
        _on(p, ISO_FX, HX - 6.5, HY + 4, 31)
        p.setBrush(QBrush(CHAIR_DARK))
        p.drawRoundedRect(QRectF(0, 0, 13, 17), 3, 3)
        p.setBrush(QBrush(CHAIR))
        p.drawRoundedRect(QRectF(1.8, 2.4, 9.4, 10), 2, 2)
        p.restore()
        if not present:
            p.restore()                             # 收掉上面那层给空椅子的淡化

        if self._say:       # 气泡:压在所有东西之上,尖尖落在人头顶稍上方
            bubble.draw(p, self._say, QPointF(SEAT_W * 0.33, 18.0))



    # ---------- 交互 ----------
    def hoverEnterEvent(self, e):
        self._hover = True
        self._sync_tip(self.hit(e.pos()))
        self.update()

    def hoverMoveEvent(self, e):
        self._sync_tip(self.hit(e.pos()))

    def hoverLeaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            # 右键只该弹菜单,不挡掉会被当成「点工位」把控制台最大化。
            e.ignore()
            return
        if self.hit(e.pos()) == "speaker":
            self.speaker_clicked.emit(self.name)
            e.accept(); return
        if self.is_up():
            self.clicked.emit(self.name)
        self._press_pos = self.pos()    # 记下起点,松手时判断到底有没有挪
        super().mousePressEvent(e)      # 空白处 = 拖动

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        super().mouseReleaseEvent(e)
        # 只有真挪过才算「拖完了」:不判断的话,点一下工位就写一次盘。
        start = self._press_pos
        self._press_pos = None
        if start is not None and start != self.pos():
            self.moved.emit(self.name)
