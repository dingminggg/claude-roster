"""本地服务(mysql / redis / apache)的清单和探活。纯逻辑,不 import Qt,可单测。

**只探,不启停**:启停服务要管理员权限,而且在一块看板上误点一下就把 MySQL 关了,
代价太大。所以这里只有读。

探法一律是 **TCP connect**,与装的是 Laragon / XAMPP / 手装无关——查进程名会把
「进程起来了但端口还没听」报成假绿,查 Windows 服务则漏掉命令行拉起来的实例。

坏配置一律退回内置缺省、绝不抛(与 `layout.py` / `peers.py` 同口径):这是块
状态看板,不能因为 yaml 写错就打不开办公室。
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

UP, DOWN, STUCK = "up", "down", "stuck"
# **别调小**:Windows 连本机一个关掉的端口会先重试 SYN ~2 秒才回「连接被拒」。
# 超时短于这个数,每个停掉的服务都会被误判成「无响应」(琥珀),永远看不到灭灯。
# 代价由 probe_all 的并发兜住:一轮的耗时是最慢那个,不是几个相加。
TIMEOUT = 2.5
MAX_SERVICES = 12       # 机房里再多就不是「一眼看全」了


@dataclass(frozen=True)
class Service:
    name: str
    port: int
    host: str = "127.0.0.1"

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


DEFAULTS = (
    Service("mysql", 3306),
    Service("redis", 6379),
    Service("apache", 80),
)


def load(path: str | Path = "services.yaml") -> list[Service]:
    """读服务清单;文件不在、读不动、格式不对 → 内置那三个。

    yaml 形如:
        services:
          - {name: mysql, port: 3306}
          - {name: pg, port: 5432, host: 127.0.0.1}
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        items = raw.get("services")
        if not isinstance(items, list):
            return list(DEFAULTS)
        out, seen = [], set()
        for it in items:
            svc = _one(it)
            if svc is not None and svc.name not in seen:
                seen.add(svc.name)
                out.append(svc)
        return out[:MAX_SERVICES] or list(DEFAULTS)
    except Exception:
        return list(DEFAULTS)


def _one(it) -> Service | None:
    """一条配置 → Service;形状不对返回 None(丢这一条,不是丢整份)。"""
    if not isinstance(it, dict):
        return None
    name = str(it.get("name") or "").strip()
    port = it.get("port")
    if not name or isinstance(port, bool) or not isinstance(port, int):
        return None
    if not (0 < port < 65536):
        return None
    host = str(it.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    return Service(name=name, port=port, host=host)


def probe(svc: Service, timeout: float = TIMEOUT) -> str:
    """一个服务的状态。

    - `UP`    连上了 = 端口听得到
    - `DOWN`  连接被拒 = 没在跑(最常见的那种「没起来」)
    - `STUCK` 超时 / 其它错 = 端口在但不搭理你(防火墙吞了、进程僵住),
              这和「没跑」不是一回事,画面上给琥珀而不是灭灯。
    """
    try:
        with socket.create_connection((svc.host, svc.port), timeout):
            return UP
    except (ConnectionRefusedError, OSError) as e:
        return DOWN if isinstance(e, ConnectionRefusedError) else STUCK
    except Exception:
        return STUCK


def probe_all(services, timeout: float = TIMEOUT) -> dict[str, str]:
    """整份清单的状态。

    **并发探**:单个 probe 最坏要等一个 TIMEOUT(见上面那条 Windows SYN 重试),
    串起来跑三个服务就是 7 秒多、比探测周期还长,一轮压着一轮。并发之后一轮的
    耗时就是最慢的那一个。

    **调用方仍要把它丢到后台线程**:这里会站住好几秒,放主线程就是界面卡死。
    """
    svcs = list(services)
    if not svcs:
        return {}
    with ThreadPoolExecutor(max_workers=len(svcs)) as pool:
        states = pool.map(lambda s: probe(s, timeout), svcs)
        return {s.name: st for s, st in zip(svcs, states)}
