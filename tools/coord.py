"""游戏世界坐标 (x, z) → 底图 SVG 用户坐标系 的仿射变换。

推导依据 the-hideout/tarkov-dev 的 ``src/pages/map/index.jsx``：

1. 标记点以 ``pos(position)`` 转成 ``latLng(lat=z, lng=x)``。
2. 投影先按 ``coordinateRotation`` 旋转：
   ``X' = x·cos - z·sin``，``Z' = x·sin + z·cos``。
3. 再走 Leaflet ``CRS.Simple`` 的 transformation ``[t0, t1, t2, t3]``
   （``scaleX = t0``，``scaleY = -t2``，``marginX = t1``，``marginY = t3``）：
   ``pixelX = t0·X' + t1``，``pixelY = -t2·Z' + t3``。
4. 底图 SVG 用 ``L.svgOverlay`` 铺满 ``bounds`` 两个角点在 pixel 空间构成的矩形
   （``getBounds`` 把 ``bounds`` 两点转成 LatLngBounds，取 NW/SE 两点；
   ImageOverlay 再把 SVG 拉伸到该两点在 pixel 空间的包围盒）。

于是「世界坐标 → SVG 用户坐标」是纯线性的，可展开成 6 个系数：

    svgX = a·x + b·z + c
    svgY = d·x + e·z + f

前端只需做 2 次乘法 + 2 次加法，无需再关心旋转与 Leaflet 的缩放。
"""

from __future__ import annotations

import math

# 90° 整数倍旋转用精确值，避免 sin(π) 浮点噪声混进数据文件
_EXACT_COS_SIN = {
    0: (1.0, 0.0),
    90: (0.0, 1.0),
    180: (-1.0, 0.0),
    270: (0.0, -1.0),
}


def _cos_sin(rotation_deg):
    """返回 (cos, sin)；90° 的整数倍取精确值。"""
    rot = float(rotation_deg or 0) % 360.0
    if rot in _EXACT_COS_SIN:
        return _EXACT_COS_SIN[rot]
    rad = math.radians(rot)
    return math.cos(rad), math.sin(rad)


def world_to_pixel(x, z, transform, coordinate_rotation=0):
    """(x, z) → Leaflet layer pixel（不含 map 缩放，缩放对本变换无影响）。"""
    t0, t1, t2, t3 = transform
    cos_a, sin_a = _cos_sin(coordinate_rotation)
    xr = x * cos_a - z * sin_a
    zr = x * sin_a + z * cos_a
    return t0 * xr + t1, -t2 * zr + t3


def compute_world_to_svg(transform, coordinate_rotation, bounds, viewbox):
    """把世界坐标 → SVG 用户坐标的变换展开成 6 个仿射系数。

    transform           : [t0, t1, t2, t3]，来自每图配置
    coordinate_rotation : 度；缺失时视为 0
    bounds              : [[x1, z1], [x2, z2]]，每图配置里的世界坐标包围矩形
    viewbox             : [minX, minY, width, height]，底图 SVG 的 viewBox

    返回 ``{"a": …, "b": …, "c": …, "d": …, "e": …, "f": …}``。
    """
    (x1, z1), (x2, z2) = bounds
    vb_w, vb_h = float(viewbox[2]), float(viewbox[3])
    if vb_w <= 0 or vb_h <= 0:
        raise ValueError("viewBox 宽高必须为正: %r" % (viewbox,))

    # LatLngBounds 由 bounds 两点构成：NW = (lat=max z, lng=min x)，SE = (lat=min z, lng=max x)
    corners = [(min(x1, x2), max(z1, z2)), (max(x1, x2), min(z1, z2))]
    pixels = [world_to_pixel(cx, cz, transform, coordinate_rotation) for cx, cz in corners]

    left = min(p[0] for p in pixels)
    right = max(p[0] for p in pixels)
    top = min(p[1] for p in pixels)
    bottom = max(p[1] for p in pixels)
    span_x, span_y = right - left, bottom - top
    if span_x <= 0 or span_y <= 0:
        raise ValueError("bounds 在 pixel 空间退化: %r" % (bounds,))

    kx, ky = vb_w / span_x, vb_h / span_y
    t0, t1, t2, t3 = transform
    cos_a, sin_a = _cos_sin(coordinate_rotation)

    return {
        "a": t0 * cos_a * kx,
        "b": -t0 * sin_a * kx,
        "c": (t1 - left) * kx,
        "d": -t2 * sin_a * ky,
        "e": -t2 * cos_a * ky,
        "f": (t3 - top) * ky,
    }


def world_to_svg(coeff, x, z):
    """按系数把世界坐标 (x, z) 变换到 SVG 用户坐标。"""
    return (
        coeff["a"] * x + coeff["b"] * z + coeff["c"],
        coeff["d"] * x + coeff["e"] * z + coeff["f"],
    )
