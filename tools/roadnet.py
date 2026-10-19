#!/usr/bin/env python3
"""构建期：把矢量底图里的道路与可通行区域栅格化成**静态路网**，供前端做同层沿道路寻路。

为什么放在构建期：运行期必须完全离线、零第三方库。前端只有 DOMParser 和画布，
没有做多边形栅格化的能力（也不该有）。这里把 SVG 解析 + 栅格化一次做完，前端只要
加载几张几 KB 的位图，再做一次加权 A*。

数据来源就是仓库里已有的 ``assets/maps/*.svg``（底图，构建期已下载），本工具**不联网**。

产物：
- ``assets/roadnet/<图 key>/<楼层组 id>.bin``：每格 2 bit 的通行代价码，行优先、
  按 ``idx = j*w + i`` 排布，4 格一字节（低位在前，第 k 格占 ``(k & 3) * 2`` 位）。
- ``data/roadnet.json``：索引（原点、格子边长、宽高、字节数、各类格子计数）。

格子码（前端映射成行走代价）：
  0 = 不可通行（水域、地图边界、地形多边形之外）
  1 = 道路（道路折线与铺装道路面）——最便宜，寻路优先走它
  2 = 可通行地形（地面、铺装、地板、楼梯、木栈道）
  3 = 难走但可穿越（建筑、岩石、树林、雷区、栅栏、墙）

分类依据是底图里的 **CSS 类**（``<g class="road_tarmac road_small">``）：组名各图不统一
（``Roads`` / ``road`` / ``Highways`` / ``Dirt_Roads``…），而类名出自 tarkov.dev 的统一
图纸规范，10 张矢量图完全一致，比组名可靠得多。瓦片底图（实验室 / 迷宫 / 破冰船）没有
``<path>``，不会产出路网，前端对这些图自然回落到直线。

用法::

    python tools/roadnet.py                # 读 data/maps.json，重建全部路网
    python tools/roadnet.py --maps customs,woods
    python tools/roadnet.py --check        # 只校验已有产物，不重建
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_data import write_atomic  # noqa: E402  —— 复用同一套「先写临时文件再替换」

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MAPS_INDEX = DATA_DIR / "maps.json"
ROADNET_DIR = ROOT / "assets" / "roadnet"
ROADNET_INDEX = DATA_DIR / "roadnet.json"

SCHEMA = 1

CODE_BLOCK, CODE_ROAD, CODE_TERRAIN, CODE_ROUGH = 0, 1, 2, 3

# --------------------------------------------------------------------------- #
# 语义表：CSS 类名 → 几何语义
# --------------------------------------------------------------------------- #
# 描边（开放折线，即道路中心线 / 障碍线）
LINE_ROAD = {"road_tarmac", "road_gravel", "road_small", "road_medium", "road_large", "railroad"}
LINE_ROUGH = {"fence", "wall"}
LINE_BLOCK = {"map_border"}
# 没被下面任何一张表命中的类（``powerline`` / ``shadow`` / ``chopper``）一律忽略：
# 它们要么是装饰（电线、阴影、直升机残骸），要么本就该由相邻的道路/地形覆盖。

# 填充（闭合多边形）
FILL_TERRAIN = {"land", "cement", "gravel", "wood", "floor", "stairs"}
FILL_ROAD = {"tarmac"}
FILL_ROUGH = {"building", "locked", "structure", "misc", "plane", "trees", "rock", "danger", "danger_small"}
FILL_BLOCK = {"water"}

# 描边宽度（底图用户单位；与 style 块里的定义一致），乘 2 即走廊宽度
WIDTH_BY_CLASS = {"road_small": 5.0, "road_medium": 8.0, "road_large": 12.0}
ROAD_WIDTH_DEFAULT = 5.0
LINE_HALF_WIDTH = {"fence": 0.5, "wall": 0.1, "map_border": 1.0, "railroad": 1.5}

# 绘制顺序：后画的覆盖先画的，用**语义优先级**而不是文档顺序——各图的文档顺序并不统一
# （灯塔的 ``water`` 画在 ``land`` 之前当海面底色，海关的 ``water`` 却画在 ``land`` 之后
# 当河塘挖洞），照文档顺序栅格化必然有一类图出错。
#
# 唯一需要看文档顺序的是 water：**画在第一个地面图元之前的水面 = 背景海面**
# （灯塔的 7 顶点大三角就是它），它在真实底图里被后画的陆地盖住，而我们的默认码 0
# 本来就已经表示「禁行」，所以这类水面直接跳过，别让它在最后一趟把陆地反盖成海。
# 画在地面之后的水面才是真正要从陆地里挖掉的水塘，放在最后压上去。
PASSES = (
    (CODE_TERRAIN, "fill", FILL_TERRAIN),
    (CODE_ROAD, "fill", FILL_ROAD),
    (CODE_ROAD, "line", LINE_ROAD),
    (CODE_ROUGH, "fill", FILL_ROUGH),
    (CODE_ROUGH, "line", LINE_ROUGH),
    (CODE_BLOCK, "fill", FILL_BLOCK),
    (CODE_BLOCK, "line", LINE_BLOCK),
)

MAX_CELLS = 400_000          # 单层格数上限（控制内存与文件体积）
SHORT_SIDE_CELLS = 250       # 短边大致切多少格
CURVE_MIN_STEPS = 4
CURVE_MAX_STEPS = 32

# --------------------------------------------------------------------------- #
# SVG 扫描
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<(/?)(\w+)((?:\"[^\"]*\"|[^>\"])*?)(/?)>", re.S)
_TOK_RE = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_ARITY = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}
_SKIP_SUBTREE = ("defs", "clipPath", "symbol", "mask", "pattern", "marker",
                 "linearGradient", "radialGradient", "filter", "style",
                 "title", "desc", "metadata")


def _attr(attrs, name):
    m = re.search(r'\b%s="([^"]*)"' % name, attrs)
    return m.group(1) if m else None


def _classes(raw):
    return set((raw or "").split())


def resolve_classes(leaf_classes, chain):
    """取「最近的非空类」：先看元素自己的 class，再逐层往上找。

    不能简单地把整条祖先链的类并起来 —— 海关一层楼的 ``Buildings-1`` 是 ``floor``（地板），
    里面嵌的 ``XX-1f-locked`` 是 ``locked``（上锁房间），并集会把两者混成一个语义。
    """
    if leaf_classes:
        return leaf_classes
    for classes in reversed(chain):
        if classes:
            return classes
    return set()


def scan_layers(text):
    """把底图切成「顶层组 → 几何叶子」，并解析每个叶子的类与路径数据。

    顶层 ``<g>`` 就是一层（``Ground_Level`` / ``Second_Floor`` …），与前端切层方式一致。
    返回 ``{层级 id: [{"classes": set, "d": str, "style": str}], …}``。
    """
    layers: "OrderedDict[str, list]" = OrderedDict()
    chain: list[tuple[str, set]] = []
    depth = 0
    skip_level = None
    for m in _TAG_RE.finditer(text):
        closing, name, attrs, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        if closing:
            depth = max(0, depth - 1)
            if skip_level is not None and depth < skip_level:
                skip_level = None
            if name == "g" and chain:
                chain.pop()
            continue
        opens = not selfclose
        if opens:
            depth += 1
        if name in _SKIP_SUBTREE:
            if skip_level is None:
                skip_level = depth
            continue
        if skip_level is not None:
            continue
        if name == "svg":
            continue
        if name == "g":
            chain.append((_attr(attrs, "id") or "", _classes(_attr(attrs, "class"))))
            continue
        if name not in ("path", "polygon", "polyline") or not chain:
            continue
        layer_id = chain[0][0]
        if not layer_id:
            continue
        if name == "path":
            d = _attr(attrs, "d") or ""
        else:
            pts = _attr(attrs, "points") or ""
            pairs = pts.replace(",", " ").split()
            coords = []
            for k in range(0, len(pairs) - 1, 2):
                coords.append("%s %s" % (pairs[k], pairs[k + 1]))
            closed = name == "polygon"
            d = "M" + " L".join(coords) + (" Z" if closed else "")
        if not d:
            continue
        layers.setdefault(layer_id, []).append({
            "classes": resolve_classes(_classes(_attr(attrs, "class")), [c for _, c in chain]),
            "d": d,
            "style": _attr(attrs, "style") or "",
        })
    return layers


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
def _flatten_cubic(p0, c1, c2, p1, steps):
    out = []
    for s in range(1, steps + 1):
        t = s / steps
        mt = 1.0 - t
        a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
        out.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p1[0],
                    a * p0[1] + b * c1[1] + c * c2[1] + d * p1[1]))
    return out


def _flatten_quad(p0, c, p1, steps):
    out = []
    for s in range(1, steps + 1):
        t = s / steps
        mt = 1.0 - t
        out.append((mt * mt * p0[0] + 2 * mt * t * c[0] + t * t * p1[0],
                    mt * mt * p0[1] + 2 * mt * t * c[1] + t * t * p1[1]))
    return out


def _curve_steps(p0, p1, cell):
    """曲线采样步数：按两端距离给个够用的步数，别把长曲线采成折线。"""
    span = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    steps = int(span / max(cell, 1e-6) / 2.0) + CURVE_MIN_STEPS
    return max(CURVE_MIN_STEPS, min(CURVE_MAX_STEPS, steps))


def parse_path(d, cell):
    """把 ``d`` 展开成子路径列表：``[{"pts": [(x, y), …], "closed": bool}, …]``。

    底图里实际只用到 ``M/m L/l H/h V/v C/c S/s Z/z``（实测无弧线、无二次曲线，
    保险起见仍支持 ``Q/T``；真遇到 ``A`` 直接跳过该子路径而不是瞎猜）。
    """
    toks = _TOK_RE.findall(d)
    out = []
    pts: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    prev_ctrl = None
    cmd = ""

    def flush(closed):
        if pts:
            out.append({"pts": list(pts), "closed": closed})
        pts.clear()

    i = 0
    total = len(toks)
    while i < total:
        tok = toks[i]
        if tok and tok[0].isalpha():
            cmd = tok
            i += 1
            if cmd in "zZ":
                flush(True)
                cur = start
                continue
            continue
        if not cmd:
            break
        lower = cmd.lower()
        n = _ARITY.get(lower, 0)
        if n == 0:
            i += 1
            continue
        if i + n > total:
            break
        try:
            args = [float(x) for x in toks[i:i + n]]
        except ValueError:
            break
        i += n
        rel = cmd.islower()
        x0, y0 = cur
        if lower == "a":
            continue                                  # 底图里不该出现；真出现就丢掉这段
        if lower == "m":
            flush(False)
            cur = (x0 + args[0] if rel else args[0], y0 + args[1] if rel else args[1])
            start = cur
            pts.append(cur)
            cmd = "l" if rel else "L"               # 后续坐标对按 lineto 处理
            prev_ctrl = None
        elif lower == "l":
            cur = (x0 + args[0] if rel else args[0], y0 + args[1] if rel else args[1])
            pts.append(cur)
            prev_ctrl = None
        elif lower == "h":
            cur = (x0 + args[0] if rel else args[0], y0)
            pts.append(cur)
            prev_ctrl = None
        elif lower == "v":
            cur = (x0, y0 + args[0] if rel else args[0])
            pts.append(cur)
            prev_ctrl = None
        elif lower == "c":
            if rel:
                c1 = (x0 + args[0], y0 + args[1])
                c2 = (x0 + args[2], y0 + args[3])
                end = (x0 + args[4], y0 + args[5])
            else:
                c1, c2, end = (args[0], args[1]), (args[2], args[3]), (args[4], args[5])
            pts.extend(_flatten_cubic(cur, c1, c2, end, _curve_steps(cur, end, cell)))
            prev_ctrl = c2
            cur = end
        elif lower == "s":
            c1 = (2 * x0 - prev_ctrl[0], 2 * y0 - prev_ctrl[1]) if prev_ctrl else cur
            if rel:
                c2 = (x0 + args[0], y0 + args[1])
                end = (x0 + args[2], y0 + args[3])
            else:
                c2, end = (args[0], args[1]), (args[2], args[3])
            pts.extend(_flatten_cubic(cur, c1, c2, end, _curve_steps(cur, end, cell)))
            prev_ctrl = c2
            cur = end
        elif lower == "q":
            ctrl = (x0 + args[0], y0 + args[1]) if rel else (args[0], args[1])
            end = (x0 + args[2], y0 + args[3]) if rel else (args[2], args[3])
            pts.extend(_flatten_quad(cur, ctrl, end, _curve_steps(cur, end, cell)))
            prev_ctrl = ctrl
            cur = end
        elif lower == "t":
            ctrl = (2 * x0 - prev_ctrl[0], 2 * y0 - prev_ctrl[1]) if prev_ctrl else cur
            end = (x0 + args[0], y0 + args[1]) if rel else (args[0], args[1])
            pts.extend(_flatten_quad(cur, ctrl, end, _curve_steps(cur, end, cell)))
            prev_ctrl = ctrl
            cur = end
    flush(False)
    return out


# --------------------------------------------------------------------------- #
# 栅格
# --------------------------------------------------------------------------- #
class Grid:
    """按 ``viewBox`` 铺开的一张方格网；每格一个 2 bit 通行码。"""

    def __init__(self, viewbox, cell):
        self.ox, self.oy = float(viewbox[0]), float(viewbox[1])
        self.cell = float(cell)
        self.w = max(1, int(math.ceil(float(viewbox[2]) / self.cell)))
        self.h = max(1, int(math.ceil(float(viewbox[3]) / self.cell)))
        self.codes = bytearray(self.w * self.h)

    # -- 坐标换算 --------------------------------------------------------- #
    def _mark(self, out, x, y):
        i = int((x - self.ox) / self.cell)
        j = int((y - self.oy) / self.cell)
        if 0 <= i < self.w and 0 <= j < self.h:
            out.add(j * self.w + i)

    def _line(self, out, p0, p1):
        x0, y0 = p0
        x1, y1 = p1
        steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / (self.cell * 0.5)))
        for s in range(steps + 1):
            t = s / steps
            self._mark(out, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    # -- 填充（扫描线 + 奇偶规则）---------------------------------------- #
    def fill_path(self, subpaths, code):
        edges = []
        for sub in subpaths:
            pts = sub["pts"]
            if len(pts) < 3:
                continue
            for k in range(len(pts)):
                x0, y0 = pts[k]
                x1, y1 = pts[(k + 1) % len(pts)]
                if y0 != y1:
                    edges.append((x0, y0, x1, y1))
        if not edges:
            return
        starts: list[list] = [[] for _ in range(self.h)]
        for x0, y0, x1, y1 in edges:
            if y0 <= y1:
                ymin, ymax, xt, slope = y0, y1, x0, (x1 - x0) / (y1 - y0)
            else:
                ymin, ymax, xt, slope = y1, y0, x1, (x0 - x1) / (y0 - y1)
            r_lo = int(math.ceil((ymin - self.oy) / self.cell - 0.5))
            r_hi = int(math.ceil((ymax - self.oy) / self.cell - 0.5)) - 1
            if r_hi < 0 or r_lo >= self.h:
                continue
            starts[max(0, r_lo)].append((min(self.h - 1, r_hi), xt, ymin, slope))
        active: list = []
        for r in range(self.h):
            if starts[r]:
                active.extend(starts[r])
            if not active:
                continue
            if any(e[0] < r for e in active):
                active = [e for e in active if e[0] >= r]
            if not active:
                continue
            yc = self.oy + (r + 0.5) * self.cell
            xs = sorted(e[1] + (yc - e[2]) * e[3] for e in active)
            row = r * self.w
            for k in range(0, len(xs) - 1, 2):
                i0 = int(math.ceil((xs[k] - self.ox) / self.cell - 0.5))
                i1 = int(math.ceil((xs[k + 1] - self.ox) / self.cell - 0.5)) - 1
                i0 = max(0, i0)
                i1 = min(self.w - 1, i1)
                if i1 >= i0:
                    self.codes[row + i0:row + i1 + 1] = bytes([code]) * (i1 - i0 + 1)

    # -- 描边（折线加粗）-------------------------------------------------- #
    def stroke_path(self, subpaths, code, half_width):
        cells: set[int] = set()
        for sub in subpaths:
            pts = sub["pts"]
            if not pts:
                continue
            if len(pts) == 1:
                self._mark(cells, pts[0][0], pts[0][1])
                continue
            seq = list(pts)
            if sub["closed"]:
                seq.append(pts[0])
            for k in range(len(seq) - 1):
                self._line(cells, seq[k], seq[k + 1])
        if not cells:
            return
        r = int(math.ceil(half_width / self.cell - 0.5))
        if r > 0:
            wide: set[int] = set()
            for idx in cells:
                j, i = divmod(idx, self.w)
                for dj in range(-r, r + 1):
                    jj = j + dj
                    if not 0 <= jj < self.h:
                        continue
                    base = jj * self.w
                    for di in range(-r, r + 1):
                        ii = i + di
                        if 0 <= ii < self.w:
                            wide.add(base + ii)
            cells = wide
        for idx in cells:
            self.codes[idx] = code

    # -- 统计 ------------------------------------------------------------- #
    def counts(self):
        """各类格子数 + 连通块数（可通行格连成的区域个数）与最大连通块面积。

        连通块是给「这条路网到底能不能走通」把关用的：上层楼只有楼梯与地板时区块会碎，
        但只要主层的最大连通块覆盖了绝大部分可通行格，寻路就不会动不动回落成直线。
        """
        out = [0, 0, 0, 0]
        for code in self.codes:
            out[code] += 1
        seen = bytearray(self.w * self.h)
        components = 0
        largest = 0
        for start in range(self.w * self.h):
            if seen[start] or not self.codes[start]:
                continue
            components += 1
            size = 0
            seen[start] = 1
            stack = [start]
            while stack:
                cur = stack.pop()
                size += 1
                j, i = divmod(cur, self.w)
                if i > 0 and not seen[cur - 1] and self.codes[cur - 1]:
                    seen[cur - 1] = 1
                    stack.append(cur - 1)
                if i + 1 < self.w and not seen[cur + 1] and self.codes[cur + 1]:
                    seen[cur + 1] = 1
                    stack.append(cur + 1)
                if j > 0 and not seen[cur - self.w] and self.codes[cur - self.w]:
                    seen[cur - self.w] = 1
                    stack.append(cur - self.w)
                if j + 1 < self.h and not seen[cur + self.w] and self.codes[cur + self.w]:
                    seen[cur + self.w] = 1
                    stack.append(cur + self.w)
            largest = max(largest, size)
        return {"blocked": out[CODE_BLOCK], "road": out[CODE_ROAD],
                "terrain": out[CODE_TERRAIN], "rough": out[CODE_ROUGH],
                "components": components, "largest": largest}


# --------------------------------------------------------------------------- #
# 构建
# --------------------------------------------------------------------------- #
def pick_cell(viewbox):
    """挑格子边长：短边大致切 :data:`SHORT_SIDE_CELLS` 格，夹在 0.5~4 之间，再按格数上限放大。

    底图用户单位基本等于「米」（``worldToSvg`` 的缩放系数实测在 1.0 附近），
    所以这个边长同时也是「每格多少米」。0.5 是工厂图（viewBox 只有 130×141）需要的细度，
    4.0 是森林 / 灯塔这类大图的上限（再细就是白白多几倍体积）。
    """
    vbw, vbh = float(viewbox[2]), float(viewbox[3])
    cell = max(0.5, min(4.0, min(vbw, vbh) / float(SHORT_SIDE_CELLS)))
    while int(math.ceil(vbw / cell)) * int(math.ceil(vbh / cell)) > MAX_CELLS:
        cell *= 1.25
    return cell


def _inline_stroke_width(style):
    m = re.search(r"stroke-width\s*:\s*([\d.]+)", style or "")
    return float(m.group(1)) if m else None


def _half_width(classes, style):
    if classes & LINE_ROAD:
        explicit = _inline_stroke_width(style)
        if explicit:
            return explicit / 2.0
        widths = [WIDTH_BY_CLASS[c] for c in classes if c in WIDTH_BY_CLASS]
        return (max(widths) if widths else ROAD_WIDTH_DEFAULT) / 2.0
    for cls, half in LINE_HALF_WIDTH.items():
        if cls in classes:
            return half
    return 0.5


def _first_ground(leaves):
    """第一个「地面」图元在文档里的下标；它之前画的 water 都算背景海面。

    地面 = 地面的填充（land / 铺装 / 地板…）或道路（铺装面 / 道路线）。找不到时返回 0，
    于是 ``下标 < 0`` 恒不成立，即「认不出地面就不做这个特判」，退回到不做任何跳过。
    """
    wanted = FILL_TERRAIN | FILL_ROAD | LINE_ROAD | LINE_ROUGH
    for idx, leaf in enumerate(leaves):
        if leaf["classes"] & wanted:
            return idx
    return 0


def build_layer(layers, layer_id, viewbox, cell):
    """栅格化一层的路网；返回 ``(Grid, 叶子数)``。``layers`` 是整个底图扫出来的层表。"""
    leaves = layers.get(layer_id) or []
    grid = Grid(viewbox, cell)
    # 路径只解析一次：同一份几何要在多趟绘制里反复用；同时记住文档下标（水的特判要用）
    parsed = [(idx, leaf, parse_path(leaf["d"], cell)) for idx, leaf in enumerate(leaves)]
    ground_from = _first_ground(leaves)
    for code, kind, wanted in PASSES:
        for idx, leaf, subpaths in parsed:
            classes = leaf["classes"]
            if not classes & wanted:
                continue
            if code == CODE_BLOCK and kind == "fill" and idx < ground_from:
                continue                                  # 背景海面：默认码 0 已经表示禁行
            if kind == "fill":
                grid.fill_path(subpaths, code)
            else:
                grid.stroke_path(subpaths, code, _half_width(classes, leaf["style"]))
    return grid, len(leaves)


def encode(codes):
    """2 bit 打包：4 格一字节，低位在前。"""
    out = bytearray((len(codes) + 3) // 4)
    for idx, code in enumerate(codes):
        out[idx >> 2] |= (code & 3) << ((idx & 3) * 2)
    return bytes(out)


def build_all(maps=None, quiet=False):
    """读 ``data/maps.json``，为每张矢量图逐层生成路网，写产物并返回索引。"""
    if not MAPS_INDEX.exists():
        raise RuntimeError("缺少 data/maps.json，请先运行 tools/fetch_data.py")
    payload = json.loads(MAPS_INDEX.read_text(encoding="utf-8"))
    wanted = set(maps or [])
    index: dict = {"schema": SCHEMA, "tool": "tools/roadnet.py",
                   "generatedAt": datetime.now(timezone.utc).replace(microsecond=0)
                   .isoformat().replace("+00:00", "Z"),
                   "cellNote": "格子码 0 不可通行 / 1 道路 / 2 地形 / 3 难走，每格 2 bit 低位在前",
                   "maps": OrderedDict()}
    total_bytes = 0
    for entry in payload.get("maps") or []:
        key = entry.get("key")
        if wanted and key not in wanted:
            continue
        rel = entry.get("svg") or ""
        svg_path = ROOT / rel
        if not svg_path.exists():
            continue
        text = svg_path.read_text(encoding="utf-8", errors="replace")
        if "<path" not in text:
            if not quiet:
                print("      %-18s 瓦片底图，无矢量道路，跳过" % key)
            continue
        layers = scan_layers(text)
        viewbox = entry.get("viewBox") or [0, 0, 1, 1]
        cell = pick_cell(viewbox)
        selectable = [f.get("svgLayer") for f in
                      ((entry.get("floors") or {}).get("selectable") or [])]
        layers_index: "OrderedDict[str, dict]" = OrderedDict()
        for layer_id in selectable:
            if not layer_id:
                continue
            grid, leaf_count = build_layer(layers, layer_id, viewbox, cell)
            if not leaf_count:
                continue
            counts = grid.counts()
            blob = encode(grid.codes)
            out_path = ROADNET_DIR / key / ("%s.bin" % layer_id)
            write_atomic(out_path, blob)
            total_bytes += len(blob)
            layers_index[layer_id] = {
                "w": grid.w, "h": grid.h, "bytes": len(blob),
                "file": "assets/roadnet/%s/%s.bin" % (key, layer_id),
                "cells": counts,
            }
            if not quiet:
                print("      %-18s %-22s %3d×%-4d 单元 %5d KB 道路 %5d 地形 %6d 难走 %6d 禁行 %6d"
                      % (key, layer_id, grid.w, grid.h, len(blob) // 1024,
                         counts["road"], counts["terrain"], counts["rough"], counts["blocked"]))
        if not layers_index:
            continue
        index["maps"][key] = {
            "cell": round(cell, 4),
            "origin": [round(float(viewbox[0]), 3), round(float(viewbox[1]), 3)],
            "layers": layers_index,
        }
    write_atomic(ROADNET_INDEX, json.dumps(index, ensure_ascii=False, indent=1).encode("utf-8"))
    if not quiet:
        print("      共 %d 张图，位图合计 %.0f KB，索引 %.0f KB"
              % (len(index["maps"]), total_bytes / 1024,
                 ROADNET_INDEX.stat().st_size / 1024))
    return index


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def check(quiet=False):
    """校验索引里登记的每个位图：文件在、大小对得上、至少有一块可通行区域。"""
    if not ROADNET_INDEX.exists():
        print("缺少 data/roadnet.json")
        return 1
    index = json.loads(ROADNET_INDEX.read_text(encoding="utf-8"))
    bad = 0
    layers = 0
    for key, item in (index.get("maps") or {}).items():
        for layer_id, layer in item["layers"].items():
            layers += 1
            path = ROOT / layer["file"]
            expect = (layer["w"] * layer["h"] + 3) // 4
            cells = layer["cells"]
            if not path.exists():
                print("缺文件 %s" % layer["file"])
                bad += 1
            elif path.stat().st_size != expect or expect != layer["bytes"]:
                print("大小不符 %s：磁盘 %d / 期望 %d" % (layer["file"], path.stat().st_size, expect))
                bad += 1
            elif not cells.get("largest"):
                print("无任何可通行区域 %s/%s" % (key, layer_id))
                bad += 1
    if not quiet:
        print("校验完成：%d 个位图，%d 处异常" % (layers, bad))
    return 1 if bad else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建底图路网（离线栅格化）")
    parser.add_argument("--maps", default="", help="逗号分隔的地图 key，默认全部矢量图")
    parser.add_argument("--check", action="store_true", help="只校验产物，不重建")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check(args.quiet)
    wanted = [k.strip() for k in args.maps.split(",") if k.strip()]
    print("[路网] 栅格化矢量底图 …")
    build_all(wanted, args.quiet)
    return check(args.quiet)


if __name__ == "__main__":
    sys.exit(main())
