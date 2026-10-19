#!/usr/bin/env python3
"""楼层波段：由上游地图配置推出「哪一层对应哪个 SVG 图层、y 落在哪一层」。

背景（上游数据实测）：
- 底图 SVG 里**每一层都是顶层的一个 ``<g id="…">``**（如 ``Ground_Level`` / ``Second_Floor`` /
  ``Basement``），层内元素是它的子组，因此显隐只需切换顶层组的 ``display``。
- 上游 ``maps.json`` 的每张图带 ``svgLayer``（主层）与 ``layers[]``，
  每个 ``layers[]`` 条目又有 ``extents[]``：``{"height": [minY, maxY], "bounds": [[[x1,z1],[x2,z2],说明], …]}``。
  ``bounds`` 为空表示该高度区间整图都算这一层；非空则必须先命中其中一个矩形。
- 判定规则与上游一致：**按顺序取第一个「y 落在区间内、且（无矩形约束或 (x,z) 在某个矩形内）」的波段**，
  都不命中才落到主层（root）。

注意：部分层没有 ``svgLayer``（如储备站的 2~5 层只有瓦片，没有矢量图层），
这类层**只用于判定与提示**，不能切换底图 —— 不然会切到一张空白图。

另外，底图里偶尔会有上游 ``layers[]`` **没登记**的楼层组（如海关的 ``First_Floor`` 有两万多字符的
墙面，上游配置里却没有对应条目）。这些组也必须进可切换列表：否则它们要么被永久藏起来，
要么在切层时和别的层叠在一起。可切换列表因此由「主层 + 上游登记的层 + 底图里认得出的楼层组」合成。
"""

from __future__ import annotations

from typing import Any

# SVG 顶层组 id → 界面显示名（比上游的 "2nd Floor" 更贴近图上实际看到的东西）
FLOOR_LABELS = {
    "Ground_Level": "地面层",
    "Ground_Floor": "地面层",
    "First_Floor": "一层",
    "Second_Floor": "二层",
    "Third_Floor": "三层",
    "Fourth_Floor": "四层",
    "Fifth_Floor": "五层",
    "Technical_Floor": "技术层",
    "Basement": "地下室",
    "Underground_Level": "地下层",
    "Bunkers": "地堡",
    # 破冰船（瓦片图）：16 层甲板，组 id 由 tools/fetch_data.py 的 TILE_MAPS 指定
    "Deck_00_Control_Room": "控制室",
    "Deck_01_Engine_Room": "主机舱",
    "Deck_02_Engine_Room_Upper": "主机舱上层",
    "Deck_03_Fuel_Pumps_Lower": "燃油泵下层",
    "Deck_04_Fuel_Pumps": "燃油泵层",
    "Deck_05_Storage_Security": "仓储/安保层",
    "Deck_06_Infirmary": "医务室",
    "Deck_07_Helipad": "直升机甲板",
    "Deck_08_Gym_Canteen": "健身房/食堂",
    "Deck_09_Accommodation_Lower": "住舱下层",
    "Deck_10_Accommodation_Mid": "住舱中层",
    "Deck_11_Accommodation_Upper": "住舱上层",
    "Deck_12_Officers_Deck": "军官甲板",
    "Deck_13_Stairs_Blocked": "封锁楼梯间",
    "Deck_14_Bridge": "舰桥",
    "Deck_15_Bridge_Roof": "舰桥顶",
}

# 楼层的上下顺序（越小越靠下）：列表按钮按这个顺序从上往下排
FLOOR_ORDER = {
    "Technical_Floor": -40,
    "Bunkers": -30,
    "Basement": -20,
    "Underground_Level": -10,
    "Ground_Level": 0,
    "Ground_Floor": 0,
    "First_Floor": 1,
    "Second_Floor": 2,
    "Third_Floor": 3,
    "Fourth_Floor": 4,
    "Fifth_Floor": 5,
}


def floor_label(svg_layer: str | None, upstream_name: str | None = None) -> str:
    """给楼层起个中文名：优先按 SVG 图层 id，其次按上游层名，最后兜底。"""
    if svg_layer and svg_layer in FLOOR_LABELS:
        return FLOOR_LABELS[svg_layer]
    if upstream_name:
        return upstream_name
    return "主层"


def _bands_of_layer(layer: dict) -> list[dict[str, Any]]:
    out = []
    for extent in layer.get("extents") or []:
        height = extent.get("height")
        if not (isinstance(height, (list, tuple)) and len(height) >= 2):
            continue
        areas = []
        for box in extent.get("bounds") or []:
            if not (isinstance(box, (list, tuple)) and len(box) >= 2):
                continue
            x1, z1 = box[0][0], box[0][1]
            x2, z2 = box[1][0], box[1][1]
            areas.append([min(x1, x2), min(z1, z2), max(x1, x2), max(z1, z2)])
        out.append(
            {
                "svgLayer": layer.get("svgLayer"),
                "label": floor_label(layer.get("svgLayer"), layer.get("name")),
                "minY": float(height[0]),
                "maxY": float(height[1]),
                "areas": areas,
            }
        )
    return out


def _selectable_floors(root_layer, switchable, svg_layers) -> list[dict[str, Any]]:
    """合成「界面上能选的楼层」：主层 + 上游登记的层 + 底图里认得出的楼层组，按由下到上排。"""
    ids = []
    for svg_id in [root_layer] + [s["svgLayer"] for s in switchable]:
        if svg_id and svg_id not in ids:
            ids.append(svg_id)
    for svg_id in svg_layers:
        if svg_id in FLOOR_LABELS and svg_id not in ids:
            ids.append(svg_id)
    ids.sort(key=lambda svg_id: (FLOOR_ORDER.get(svg_id, 99), svg_id))
    return [
        {"svgLayer": svg_id, "label": floor_label(svg_id), "isRoot": svg_id == root_layer}
        for svg_id in ids
    ]


def build_floors(entry: dict, svg_layers: list[str] | None = None) -> dict[str, Any]:
    """由上游单图配置生成楼层结构。

    返回 ``{"root": 主层, "bands": [可判定层…], "switchable": [上游登记的层…],
    "selectable": [界面上可选的层…], "default": [默认显示层 id…]}``。
    """
    svg_layers = list(svg_layers or [])
    root_layer = entry.get("svgLayer")

    root = {
        "svgLayer": root_layer,
        "label": floor_label(root_layer) if root_layer else "主层",
        "minY": None,
        "maxY": None,
        "areas": [],
        "isRoot": True,
    }

    bands: list[dict[str, Any]] = []
    switchable: list[dict[str, Any]] = []
    seen: set[str] = set()
    for layer in entry.get("layers") or []:
        bands.extend(_bands_of_layer(layer))
        svg_id = layer.get("svgLayer")
        if (
            svg_id
            and svg_id != root_layer
            and svg_id not in seen
            and (not svg_layers or svg_id in svg_layers)
        ):
            seen.add(svg_id)
            switchable.append({"svgLayer": svg_id, "label": floor_label(svg_id, layer.get("name"))})

    default: list[str] = []
    if root_layer and (not svg_layers or root_layer in svg_layers):
        default.append(root_layer)
    for layer in entry.get("layers") or []:
        svg_id = layer.get("svgLayer")
        if (
            layer.get("show")
            and svg_id
            and svg_id not in default
            and (not svg_layers or svg_id in svg_layers)
        ):
            default.append(svg_id)   # 上游标记 show=true 的层默认叠加显示（如立交桥商场一层）

    return {
        "root": root,
        "bands": bands,
        "switchable": switchable,
        "selectable": _selectable_floors(root_layer, switchable, svg_layers),
        "default": default,
    }


def _inside(area: list[float], x: float, z: float) -> bool:
    return area[0] <= x <= area[2] and area[1] <= z <= area[3]


def detect_band(floors: dict, x: float | None, y: float | None, z: float | None) -> dict[str, Any]:
    """判断 (x, y, z) 落在哪一层；都不命中就返回主层。

    ``y`` 缺失（旧截图没有高度）时直接落到主层，避免拿不准就乱切。
    """
    if y is None:
        return floors["root"]
    for band in floors.get("bands") or []:
        if not (band["minY"] <= y < band["maxY"]):
            continue
        areas = band.get("areas") or []
        if not areas:
            return band
        if x is not None and z is not None and any(_inside(a, x, z) for a in areas):
            return band
    return floors["root"]


def band_key(floors: dict, band: dict) -> str:
    """波段的稳定标识：用 svgLayer，没有则用 ``label@minY`` 区分同层不同区间。"""
    return band.get("svgLayer") or "%s@%s" % (band.get("label"), band.get("minY"))
