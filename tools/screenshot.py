#!/usr/bin/env python3
"""EFT 截图文件名解析（运行期，纯标准库）

EFT 的截图文件名里带着拍摄瞬间的**相机位置与旋转**，本模块把它解析出来，
供 serve.py 通过 SSE 推给前端做实时定位。全程只读文件名、只读文件时间戳，
不读图片内容、不碰游戏进程。

## 真实格式（用 6588 张实机截图统计得出，2026-10-17）

    <日期>[<时-分>]_<x>, <y>, <z>_<q0>, <q1>, <q2>, <q3>[_<额外值>] (<去重序号>).png

例（均为真实文件名）：

    2026-09-16[20-25]_-491.46, 22.09, -49.75_0.01288, 0.43846, -0.00628, 0.89864_5.98 (0).png
    2026-09-19[10-44]_65.66, 12.04, -944.35_0.00291, -0.99382, 0.00173, 0.11091 (0).png

分布：6483 张带「位置+四元数+额外值」，10 张带「位置+四元数」，其余 95 张
**只有日期时间和一个孤零零的数字**（没有位置信息）。所以解析器必须允许失败：
拿不到完整的 3 个位置分量就不返回结果，宁可没有定位也不要误报。

## 朝向约定（用 1412 个「真实连拍相邻帧」反推确定，不是猜的）

判断方法：把截图按文件 mtime 排成真实时间序，取相邻两帧位移在 0.6~3.0 m
（即在走动）的样本对，比较「位移方向」与「四元数推导的朝向」：

| 候选约定 | 中位误差 | ≤20° 比例 |
| --- | ---: | ---: |
| 四元数 (x,y,z,w) + forward=(sin,cos) | **5.4°** | **74%** |
| 同上但 forward 取反 | 174.6° | 2% |
| 四元数 (w,x,y,z) + forward=(sin,cos) | 86.4° | 18% |

结论：四元数按 Unity 惯例存为 **(x, y, z, w)**，yaw 用绕 Y 轴公式
`atan2(2*(w*y + x*z), 1 - 2*(y*y + z*z))`，世界朝向为
`forward = (sin yaw, cos yaw)`（yaw=0 指向 +z，yaw=90° 指向 +x）。

残余误差来自玩家横移/转身时位移方向本就不等于视线方向，属正常噪声。
"""

from __future__ import annotations

import math
import os
import re
from typing import Any

# 真实文件名格式（严格到「必须同时有 3 个位置分量与 4 个四元数分量」才认）
PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\[(?P<time>\d{2}-\d{2})\]"
    r"(?:_(?P<x>-?\d+(?:\.\d+)?),\s*(?P<y>-?\d+(?:\.\d+)?),\s*(?P<z>-?\d+(?:\.\d+)?)"
    r"_(?P<q0>-?\d+(?:\.\d+)?),\s*(?P<q1>-?\d+(?:\.\d+)?),\s*(?P<q2>-?\d+(?:\.\d+)?),\s*(?P<q3>-?\d+(?:\.\d+)?)"
    r"(?:_(?P<extra>-?\d+(?:\.\d+)?))?"
    r")?"
    r"(?:\s*\((?P<dup>\d+)\))?"
    r"\.(?P<ext>png|jpg|jpeg)$",
    re.IGNORECASE,
)

IMAGE_EXTS = (".png", ".jpg", ".jpeg")


def parse_screenshot_name(name: str) -> dict[str, Any] | None:
    """解析单个文件名。

    返回 `{"x", "y", "z", "yaw", "date", "time", "name"}`；**结构不符或没有位置信息返回 None**，
    任何情况下都不抛异常（扫描目录时会遇到各种奇怪文件）。
    """
    if not isinstance(name, str):
        return None
    m = PATTERN.match(name.strip())
    if not m or m.group("x") is None:
        return None
    x, y, z = (float(m.group(k)) for k in ("x", "y", "z"))
    quat = tuple(float(m.group("q%d" % i)) for i in range(4))
    return {
        "x": x,
        "y": y,
        "z": z,
        "yaw": yaw_from_quaternion(*quat),
        "date": m.group("date"),
        "time": m.group("time"),
        "name": name,
    }


def yaw_from_quaternion(qx: float, qy: float, qz: float, qw: float) -> float:
    """Unity 四元数 (x,y,z,w) → 绕 Y 轴的朝向角（度，0 = +z，顺时针朝 +x 增大）。"""
    yaw = math.atan2(2.0 * (qw * qy + qx * qz), 1.0 - 2.0 * (qy * qy + qz * qz))
    deg = math.degrees(yaw) % 360.0
    return deg - 360.0 if deg > 180.0 else deg


def world_forward(yaw_deg: float) -> tuple[float, float]:
    """朝向角 → 世界平面上的单位朝向向量 (dx, dz)。"""
    rad = math.radians(yaw_deg)
    return math.sin(rad), math.cos(rad)


def svg_angle_degrees(coeff: dict[str, float], yaw_deg: float) -> float:
    """朝向角 → SVG 里的箭头旋转角（度）。

    必须走仿射的线性部分，不能只把 yaw 直接当屏幕角：各图底图的坐标轴方向不一致
    （如海关 a 为负，表示 x 向右时 SVG 里反而向左），只有整体变换才对齐。
    返回的角度可直接用于 SVG `rotate()`（SVG 的 y 向下，rotate 为正即顺时针）。
    """
    dx, dz = world_forward(yaw_deg)
    sx = coeff["a"] * dx + coeff["b"] * dz
    sy = coeff["d"] * dx + coeff["e"] * dz
    if sx == 0.0 and sy == 0.0:      # 理论上不会发生（仿射可逆），保守兜底
        return 0.0
    return math.degrees(math.atan2(sy, sx))


def list_screenshot_files(directory: str) -> list[tuple[float, str]]:
    """列出目录下的图片文件，按 mtime 升序返回 `[(mtime, 文件名)]`。

    注意用 **文件 mtime 当时间序**：文件名里的 `(n)` 只是同秒重名的去重序号，
    不是时间序，按它排序会得到乱序（这一点是实测踩到的）。
    """
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return []
    items = []
    for entry in entries:
        if not entry.is_file():
            continue
        if os.path.splitext(entry.name)[1].lower() not in IMAGE_EXTS:
            continue
        try:
            items.append((entry.stat().st_mtime, entry.name))
        except OSError:
            continue
    items.sort(key=lambda it: it[0])
    return items


def latest_position(directory: str) -> dict[str, Any] | None:
    """取目录里**最新一张可解析**的截图位置。

    从最新往回找，第一个能解析出位置的文件即结果；全目录都解析不出来返回 None
    （例如用户只在菜单里截图，或目录里塞满了别的图片）。
    """
    for mtime, name in reversed(list_screenshot_files(directory)):
        parsed = parse_screenshot_name(name)
        if parsed:
            parsed["mtime"] = mtime
            return parsed
    return None


# ---------------------------------------------------------------- 清理（自动删除截图）
def select_deletable(directory: str, cutoff: float | None = None, keep_newest: int = 1) -> list[str]:
    """挑出「位置已经读过、可以删掉」的截图文件名（**只挑不删**，便于单测）。

    规则：

    1. 只考虑**能解析出位置**的截图——没读到位置的文件不碰（用户手动拍的菜单截图等照旧留着）；
    2. **保留最新 `keep_newest` 个**：实时定位就靠最新那一张，删了会没位置（见 `latest_position`）；
    3. `cutoff` 是「开关打开的时刻」，**只删它之后产生的**（mtime >= cutoff），
       这样历史截图与开关关闭期间攒下的截图都不会被误删。

    返回按 mtime 升序（先旧的先删），顺序稳定便于测试与日志。
    """
    parsed: list[tuple[float, str]] = []
    for mtime, name in list_screenshot_files(directory):
        if parse_screenshot_name(name):
            parsed.append((mtime, name))

    keep = max(0, keep_newest)
    protected = {name for _, name in parsed[len(parsed) - keep:]} if keep else set()

    chosen = []
    for mtime, name in parsed:
        if name in protected:
            continue
        if cutoff is not None and mtime < cutoff:
            continue
        chosen.append(name)
    return chosen


def delete_files(directory: str, names: list[str]) -> list[str]:
    """删除给定文件名，返回**真正删掉**的那些（失败静默跳过，不抛异常）。

    删不掉通常是因为文件正被游戏占用或已被别的程序删走，跳过即可，下一轮还会再挑到。
    """
    deleted = []
    for name in names:
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            continue
        deleted.append(name)
    return deleted


def prune(directory: str, cutoff: float | None = None, keep_newest: int = 1) -> list[str]:
    """读取过位置后清掉多余截图，返回被删除的文件名。"""
    return delete_files(directory, select_deletable(directory, cutoff, keep_newest))
