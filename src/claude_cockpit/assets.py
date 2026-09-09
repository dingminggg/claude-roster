"""自带资源的路径。单独放一个模块:图标既给托盘用也给窗口用,
不该继续挂在某个具体界面模块下面(以前挂在 panel.py,那文件已退休)。"""
from pathlib import Path

ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"
