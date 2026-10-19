#!/usr/bin/env python3
"""构建期数据拉取：从 tarkov.dev 公开数据生成 ``data/maps.json`` 与 ``assets/maps/*.svg``。

联网只发生在这里；运行期（``serve.py`` / 前端）完全离线。

用法::

    python tools/fetch_data.py                # 首次拉取（幂等：已就绪则跳过）
    python tools/fetch_data.py --force        # 强制重新拉取
    python tools/fetch_data.py --maps customs,woods
    python tools/fetch_data.py --mode pve

数据来源与访问约束见 docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md §5.2。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coord import compute_world_to_svg, world_to_pixel  # noqa: E402
from floors import build_floors       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "maps"
TILE_ASSET_DIR = ASSETS_DIR / "tiles"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "build-cache"
TILE_CACHE_DIR = CACHE_DIR / "tiles"

# 1 = M1（撤离/过境/出生/地名）；2 = 加入物资、危险区、钥匙门、Boss、楼层；
# 3 = 容器带类别；4 = 容器按参考站 14 类细分 + 新增「固定武器」图层；
# 5 = 锁带钥匙名（keyName） + 新增「高级资源点」图层（valuables）；
# 6 = 收录瓦片底图的实验室 / 迷宫（构建期把上游瓦片拼成合成 SVG 底图）
SCHEMA = 6

MARKERS_URL = "https://json.tarkov.dev/{mode}/maps"
MARKERS_ZH_URL = "https://json.tarkov.dev/{mode}/maps_zh"
# 物品中文名：上锁的门只给钥匙物品 id，要在这里换成「XX 房间钥匙」才看得懂
ITEMS_ZH_URL = "https://json.tarkov.dev/{mode}/items_zh"
MAP_CONFIG_URL = "https://raw.githubusercontent.com/the-hideout/tarkov-dev/main/src/data/maps.json"
SVG_URL_TEMPLATE = "https://assets.tarkov.dev/maps/svg/{name}.svg"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 大文件（标注点原始数据约 8.7 MB）留足超时
TIMEOUT_LARGE = 300
TIMEOUT_SMALL = 90


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #
def _urllib_get(url, headers, timeout):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _curl_get(url, headers, timeout):
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("未找到 curl 可执行文件")
    cmd = [exe, "-sS", "-L", "--max-time", str(int(timeout))]
    for key, value in headers.items():
        cmd += ["-H", "%s: %s" % (key, value)]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 30)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("curl 退出码 %s：%s" % (proc.returncode, proc.stderr.decode("utf-8", "replace")[:200]))
    return proc.stdout


def fetch(url, *, browser_ua=False, timeout=TIMEOUT_SMALL):
    """下载 URL。

    实测约束：``assets.tarkov.dev`` 必须带浏览器 UA（否则 Cloudflare 403），
    ``json.tarkov.dev`` 用默认头更稳。两种头都失败时回退 ``curl.exe``
    （纯标准库在部分网络下会被 Cloudflare 以 error 1010 拦截）。
    """
    plain = {"Accept": "*/*"}
    browser = {"Accept": "*/*", "User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}
    variants = [browser, plain] if browser_ua else [plain, browser]

    errors = []
    for headers in variants:
        try:
            data = _urllib_get(url, headers, timeout)
            if data:
                return data
            errors.append("urllib 返回空内容")
        except Exception as exc:  # noqa: BLE001 - 逐个候选头都要尝试
            errors.append("%s: %s" % (type(exc).__name__, exc))
    try:
        return _curl_get(url, browser, timeout)
    except Exception as exc:  # noqa: BLE001
        errors.append("curl: %s" % exc)
    raise RuntimeError("下载失败 %s\n      - %s" % (url, "\n      - ".join(errors)))


def load_json_cached(url, cache_name, *, force, timeout, browser_ua=False):
    """优先读 build-cache/ 里的原始文件，缺失或 --force 时才联网。"""
    path = CACHE_DIR / cache_name
    if path.exists() and path.stat().st_size > 512 and not force:
        return json.loads(path.read_bytes().decode("utf-8", "replace")), path.read_bytes()
    raw = fetch(url, browser_ua=browser_ua, timeout=timeout)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return json.loads(raw.decode("utf-8", "replace")), raw


# --------------------------------------------------------------------------- #
# 解析辅助
# --------------------------------------------------------------------------- #
def parse_svg_viewbox(text):
    """从 SVG 根元素读出 viewBox；无 viewBox 时回退到 width/height。"""
    tag_match = re.search(r"<svg\b[^>]*>", text, re.S)
    if not tag_match:
        raise ValueError("文件里找不到 <svg> 根元素")
    tag = tag_match.group(0)
    vb = re.search(r'viewBox="([-\d.eE+,\s]+)"', tag)
    if vb:
        nums = [float(part) for part in re.split(r"[,\s]+", vb.group(1).strip()) if part]
        if len(nums) == 4:
            return nums
    width = re.search(r'\bwidth="([\d.]+)"', tag)
    height = re.search(r'\bheight="([\d.]+)"', tag)
    if width and height:
        return [0.0, 0.0, float(width.group(1)), float(height.group(1))]
    raise ValueError("SVG 既无 viewBox 也无 width/height")


def prettify_key(key):
    """``ground-zero`` → ``Ground Zero``（中文名缺失时的兜底显示名）。"""
    return " ".join(word.capitalize() for word in key.split("-"))


def parse_svg_top_layers(text):
    """列出 SVG 根下**顶层**的 ``<g id="…">``。

    底图里每一层都是顶层的一个组（``Ground_Level`` / ``Second_Floor`` / ``Basement``…），
    层内元素是它的子组，所以前端只需切换顶层组的 ``display`` 就能换层。
    用深度扫描而不是正则全匹配，避免把嵌套子组（Ground / Trees / Roads…）也算成一层。
    """
    tops = []
    stack_depth = 0
    for match in re.finditer(r"<g\b[^>]*>|</g\s*>", text):
        tag = match.group(0)
        if tag.startswith("</"):
            stack_depth = max(0, stack_depth - 1)
            continue
        if stack_depth == 0:
            gid = re.search(r'\bid="([^"]+)"', tag)
            if gid:
                tops.append(gid.group(1))
        if not tag.rstrip().endswith("/>"):
            stack_depth += 1     # 自闭合的 <g/> 不产生层级，否则后面的顶层组会被算成子组
    return tops


def outline_2d(points):
    """把 ``[{"x":…, "z":…}, …]`` 多边形压成 ``[[x, z], …]``。"""
    out = []
    for point in points or []:
        x, z = flatten_positions(point)
        if x is not None and z is not None:
            out.append([round(float(x), 2), round(float(z), 2)])
    return out


def point_3d(node, extra=None):
    """统一 ``{"x","y","z"}`` 取点；顺带带出要保留的其它字段。"""
    if not isinstance(node, dict):
        return None
    x, z = node.get("x"), node.get("z")
    if x is None or z is None:
        return None
    item = {"x": round(float(x), 3), "z": round(float(z), 3)}
    if node.get("y") is not None:
        item["y"] = round(float(node["y"]), 3)
    if extra:
        item.update(extra)
    return item


def localize(translations, key, fallback):
    """用中文翻译表查名字；查不到就回退，不报错。"""
    if key and isinstance(translations.get(key), str):
        return translations[key]
    return fallback


def flatten_positions(node):
    """把 ``{"x":…, "z":…}`` 或 ``[x, z]`` 统一成 ``(x, z)``。"""
    if isinstance(node, dict):
        return node.get("x"), node.get("z")
    if isinstance(node, (list, tuple)) and len(node) >= 2:
        return node[0], node[1]
    return None, None


# --------------------------------------------------------------------------- #
# 构建
# --------------------------------------------------------------------------- #
def svg_basename(entry):
    """从上游 svgPath 取底图文件名：``/maps/svg/Customs.svg`` → ``Customs.svg``。"""
    return entry["svgPath"].rstrip("/").split("/")[-1]


# --------------------------------------------------------------------------- #
# 瓦片底图（实验室 / 迷宫）
# --------------------------------------------------------------------------- #
# 这两张图上游只给瓦片（配置里没有 svgPath），而社区 SVG 仓库里的 Labs.svg 与上游 bounds
# 对不齐（实测该 SVG 的绘制内容宽高比 1.237，bounds 对应的世界矩形是 1.372，直接套现有
# 公式会把整图横向拉伸约 10%，标记肉眼可见地错位）。所以构建期把上游瓦片**按网格位置**
# 拼成一张合成底图：写一个 <svg>，每个顶层 <g> 是一层，组内按瓦片在地图像素网格里的
# 真实位置摆 <image>，引用 assets/maps/tiles/ 下的 PNG。
#
# 好处是前端**一行都不用改**：它照旧读 SVG 的 viewBox 与顶层组来切层、缩放、垫半透明，
# 只是组里的图元从矢量换成了位图。坐标则完全走上游自带的 transform + bounds——
# 每格瓦片在 base pixel 空间是确定的方格，不存在「底图与 bounds 对不齐」的问题。
#
# 清晰度与体积（实测）：上游每格瓦片是 256px 的图、覆盖 tileSize 个地图像素
# （实验室 175、迷宫 256）。zoom 取 3 时两张图各约 2000px 宽、合计约 6 MB；
# 取 4 会到约 23 MB 而屏幕上看不出明显差别，所以停在 3。
TILE_ZOOM = 3
TILE_WORKERS = 8

TILE_MAPS = {
    "the-lab": {
        "file": "TheLab.svg",
        # 上游这几层只有 name、没有 svgLayer，这里补上组 id，楼层判定与切换才能工作
        # （主层 = 一层的瓦片，其余两层是上游 layers 里的 Second Level / Technical）
        "layerIds": [(None, "First_Floor"), ("Second Level", "Second_Floor"),
                     ("Technical", "Technical_Floor")],
    },
    "the-labyrinth": {
        "file": "TheLabyrinth.svg",
        "layerIds": [(None, "Ground_Level")],
    },
}

# 上游对没有内容的格子也返回 200 + 一张全透明小图（102 字节），据此跳过空瓦片——
# 既少写文件，也让底图 SVG 里少几百个 <image>。
TILE_EMPTY_MAX = 512


def svg_num(value):
    """写进 SVG 的数值：最多 4 位小数并去掉尾随 0（体积小，也免掉浮点噪声）。"""
    text = ("%.4f" % float(value)).rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def tile_pixel_rect(transform, rotation, bounds):
    """世界坐标矩形 → 底图 base pixel 空间的包围矩形 ``(左, 上, 右, 下)``。

    与 coord.compute_world_to_svg 用同一套角点规则（取对角两点），保证两者一致。
    """
    (x1, z1), (x2, z2) = bounds
    corners = [(min(x1, x2), max(z1, z2)), (max(x1, x2), min(z1, z2))]
    pixels = [world_to_pixel(cx, cz, transform, rotation) for cx, cz in corners]
    return (min(p[0] for p in pixels), min(p[1] for p in pixels),
            max(p[0] for p in pixels), max(p[1] for p in pixels))


def tile_grid(left, top, right, bottom, tile_size, zoom):
    """某层底图矩形覆盖到的瓦片下标范围 ``(x0, x1, y0, y1)``，含压在边界上的那一圈。"""
    step = float(tile_size) / (2 ** zoom)
    return (int(math.floor(left / step)), int(math.ceil(right / step) - 1),
            int(math.floor(top / step)), int(math.ceil(bottom / step) - 1))


def layer_world_bounds(entry, layer):
    """一层的世界坐标矩形：上游给了 bounds（如实验室二层只占地面层的一角）就用它，否则整图。"""
    boxes = [box for extent in (layer or {}).get("extents") or []
             for box in (extent.get("bounds") or [])]
    if not boxes:
        return entry["bounds"]
    xs, zs = [], []
    for box in boxes:
        xs += [box[0][0], box[1][0]]
        zs += [box[0][1], box[1][1]]
    return [[min(xs), min(zs)], [max(xs), max(zs)]]


def apply_tile_layer_ids(entry, key):
    """给瓦片图补 svgLayer（就地改）：上游这些层只有 name，不补的话楼层功能整个不工作。"""
    by_name = {layer.get("name"): layer for layer in entry.get("layers") or []}
    for name, layer_id in TILE_MAPS[key]["layerIds"]:
        if name is None:
            entry["svgLayer"] = layer_id
        elif name in by_name:
            by_name[name]["svgLayer"] = layer_id


def tile_svg_document(viewbox, groups):
    """合成底图 SVG 文本：``groups`` 是 ``[(组 id, [<image> 参数…]), …]``。

    viewBox 原点固定在 0 0——coord.compute_world_to_svg 也是这么假定底图的
    （它只按 bounds 与 viewBox 的宽高算缩放），所以 image 的 x/y 是
    「瓦片左上角在像素空间的坐标减去矩形左上角」，两者严丝合缝。
    """
    width, height = viewbox[2], viewbox[3]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'width="%s" height="%s" viewBox="0 0 %s %s">'
           % (svg_num(width), svg_num(height), svg_num(width), svg_num(height))]
    for group_id, images in groups:
        out.append('<g id="%s">' % group_id)
        for image in images:
            href = image["href"]
            out.append('<image x="%s" y="%s" width="%s" height="%s" preserveAspectRatio="none" '
                       'xlink:href="%s" href="%s"/>'
                       % (svg_num(image["x"]), svg_num(image["y"]), svg_num(image["w"]),
                          svg_num(image["h"]), href, href))
        out.append('</g>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def tile_file_name(layer_id, zoom, x, y):
    return "%s_%d_%d_%d.png" % (layer_id, zoom, x, y)


def fetch_tile(url, cache_path, force):
    """下载一格瓦片：已缓存且不是 --force 就直接读缓存（空瓦片也缓存，免得每次重问一遍）。"""
    if cache_path.exists() and not force:
        return cache_path.read_bytes()
    last_error = None
    for _attempt in range(2):          # 网络抖一下很常见，重试一次；仍失败就整体报错
        try:
            raw = fetch(url, browser_ua=True, timeout=TIMEOUT_SMALL)
            write_atomic(cache_path, raw)
            return raw
        except Exception as exc:  # noqa: BLE001 - 逐个候选都要尝试
            last_error = exc
    raise RuntimeError("瓦片下载失败 %s（%s）" % (url, last_error))


def build_tile_svg(key, entry, force):
    """把一张瓦片图的所有层拼成合成底图，返回 ``(viewBox, 顶层组 id, 写入字节数)``。"""
    cfg = TILE_MAPS[key]
    tile_size = float(entry.get("tileSize") or 256)
    transform = entry.get("transform") or [1, 0, 1, 0]
    rotation = entry.get("coordinateRotation") or 0
    left, top, right, bottom = tile_pixel_rect(transform, rotation, entry["bounds"])
    if right - left <= 0 or bottom - top <= 0:
        raise ValueError("图 %s 的 bounds 在像素空间退化" % key)
    step = tile_size / float(2 ** TILE_ZOOM)     # 一格瓦片占多少 base pixel

    by_name = {layer.get("name"): layer for layer in entry.get("layers") or []}
    groups = []
    written = 0
    for name, layer_id in cfg["layerIds"]:
        layer = None if name is None else by_name.get(name)
        tile_path = entry.get("tilePath") if name is None else (layer or {}).get("tilePath")
        if not tile_path:
            raise ValueError("图 %s 的层 %s 没有 tilePath" % (key, name or "主层"))
        l, t, r, b = tile_pixel_rect(transform, rotation, layer_world_bounds(entry, layer))
        x0, x1, y0, y1 = tile_grid(l, t, r, b, tile_size, TILE_ZOOM)
        coords = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
        jobs = [(tile_path.format(z=TILE_ZOOM, x=x, y=y),
                 TILE_CACHE_DIR / key / tile_file_name(layer_id, TILE_ZOOM, x, y))
                for x, y in coords]
        with ThreadPoolExecutor(max_workers=TILE_WORKERS) as pool:
            raws = list(pool.map(lambda job: fetch_tile(job[0], job[1], force), jobs))

        images = []
        for (x, y), raw in zip(coords, raws):
            if len(raw) <= TILE_EMPTY_MAX:
                continue                     # 空格子：全透明，摆了也是白摆
            target = TILE_ASSET_DIR / key / tile_file_name(layer_id, TILE_ZOOM, x, y)
            if not target.exists() or target.read_bytes() != raw:
                write_atomic(target, raw)
            written += len(raw)
            images.append({"x": x * step - left, "y": y * step - top, "w": step, "h": step,
                           "href": "assets/maps/tiles/%s/%s" % (key, target.name)})
        groups.append((layer_id, images))
        print("      %-18s %-16s 瓦片 %3d/%3d（空格子 %d）"
              % (key, layer_id, len(images), len(coords), len(coords) - len(images)))

    write_atomic(ASSETS_DIR / cfg["file"], tile_svg_document([0.0, 0.0, right - left, bottom - top],
                                                             groups).encode("utf-8"))
    return [0.0, 0.0, right - left, bottom - top], [gid for gid, _images in groups], written


def select_maps(config, requested):
    """从上游配置里挑出能收录的图：有 SVG 底图的，加上本项目自己拼瓦片的。"""
    available = {}
    for group in config:
        for entry in group.get("maps") or []:
            if entry.get("svgPath") or entry["key"] in TILE_MAPS:
                available[entry["key"]] = entry
    if not requested:
        return available
    unknown = [key for key in requested if key not in available]
    if unknown:
        raise ValueError(
            "这些图没有可用底图：%s\n      可选：%s"
            % (", ".join(unknown), ", ".join(sorted(available)))
        )
    return {key: available[key] for key in requested}


# 物资容器的类别：前端把「物资容器」拆成这些开关，分类在构建期按容器 slug 定好。
# 用 slug（上游 lootContainers[].normalizedName，如 medbag）而不是中文译名分类——
# 同一个容器会有多种译名（medbag 就有「SMU06 医疗包」和「SMU06医疗包」两种），slug 才稳定。
# 类别与命名对齐参考站 tarkov.kaedeori.com 的图例，便于对照使用习惯。
CONTAINER_GROUPS = [
    ("safe", "保险箱", ("safe", "bank-safe")),
    ("jacket", "夹克衫", ("jacket",)),
    ("pcblock", "机箱", ("pc-block",)),
    ("scavbody", "Scav尸体", ("dead-scav", "scav-body", "pmc-body", "civilian-body",
                              "lab-technician-body")),
    ("drawer", "抽屉", ("drawer",)),
    ("duffle", "旅行包", ("duffle-bag",)),
    ("cache", "彩蛋点", ("buried-barrel-cache", "ground-cache", "shturmans-stash")),
    ("med", "医疗物资", ("medbag", "medcase", "medical-supply-crate")),
    ("supply", "物资箱", ("ration-supply-crate", "technical-supply-crate")),
    ("suitcase", "塑料手提箱", ("plastic-suitcase",)),
    ("toolbox", "工具箱", ("toolbox",)),
    ("register", "收银机", ("cash-register", "bank-cash-register")),
    ("grenade", "手雷箱", ("grenade-box",)),
    # 木制板条箱内容只出弹药、木制弹药箱同源，按用户口径一并归入「武器箱」
    ("weapon", "武器箱", ("weapon-box", "wooden-crate", "wooden-ammo-box")),
]

# 认不出的 slug（上游随时可能新增容器）兜底到这一类，保证一个点位都不丢
CONTAINER_FALLBACK = ("misc", "其他容器")

CONTAINER_SLUG_GROUP = {slug: key for key, _label, slugs in CONTAINER_GROUPS for slug in slugs}

CONTAINER_LABELS = {key: label for key, label, _slugs in CONTAINER_GROUPS}
CONTAINER_LABELS[CONTAINER_FALLBACK[0]] = CONTAINER_FALLBACK[1]


def container_group(slug):
    """容器 slug → 类别 key；认不出的归「其他容器」，不丢点。"""
    return CONTAINER_SLUG_GROUP.get(slug or "", CONTAINER_FALLBACK[0])


# 高级资源点的判定名单：散落刷点（lootLoose）的物品池里出现下列任一名字就算「高级资源点」。
# 用**中文物品名**而不是 id：id 会随上游版本变，名字更稳、也方便以后手动增删。
HIGH_VALUE_ITEMS = (
    # 硬通货
    "实体比特币", "“凶狠跑刀崽”私酒", "LEDX皮肤透照仪", "便携式除颤器",
    # 颜色钥匙卡与稀有钥匙卡
    "实验室钥匙卡·红", "实验室钥匙卡·蓝", "实验室钥匙卡·黄", "实验室钥匙卡·紫",
    "实验室钥匙卡·绿", "实验室钥匙卡·黑",
    "Object #21WS 钥匙卡", "Object #11SR 钥匙卡",
    "TerraGroup 实验室生活区钥匙卡", "Boreas 破冰船载员舱钥匙卡",
    "Boreas 破冰船轮机舱钥匙卡", "C-1 舱室钥匙卡",
    # 稀有钥匙
    "生锈的带血钥匙",
    # ------------------------------------------------------------------ #
    # 2026-10-18 追加：**固定刷新的钥匙**
    # 口径（用户定）：只收录「刷点物品池里只有它自己」的钥匙——这类点必定刷出该钥匙，
    # 是玩家真正会去蹲的点。全池钥匙（口径 C）不收录，避免把随机刷点也算成高级资源点。
    # 判定与生成过程见 AGENT_HANDOFF.md §6.9；清单由 build-cache 里的 markers-regular.json
    # （lootLoose[].items 长度 == 1）离线算出，可复现。
    "公寓管理员钥匙", "Knossos LLC 设施钥匙", "休息室钥匙", "公司主管办公室钥匙",
    "军事基地检查站钥匙", "别墅后门钥匙", "手术室钥匙", "停尸房钥匙",
    "不动产管理处办公室钥匙", "海关 Tarcone 主管办公室钥匙",
    "“调解室”钥匙",
    "宿舍104房间钥匙", "宿舍110房间钥匙", "宿舍203房间钥匙", "宿舍220房间钥匙",
    "宿舍303房间钥匙",
    "一号房钥匙", "二号房钥匙", "三号房钥匙", "四号房钥匙",
    "酒店215房间钥匙",
    "EMERCOM医疗区钥匙", "IDEA收银机钥匙", "OLI收银机钥匙", "OLI物流部钥匙",
    "OLI超市杂物间钥匙", "X光检查室钥匙", "Primorsky 46-48号天桥钥匙",
    "RB-KORL钥匙", "RB-OB钥匙", "RB-ORB1钥匙", "RB-ORB2钥匙", "RB-ORB3钥匙",
    "RB-PSV1钥匙", "RB-ST钥匙", "RB-TB钥匙",
    "TerraGroup 实验室军械库钥匙", "TerraGroup 实验室武器测试区域钥匙",
    "TerraGroup 实验室经理办公室钥匙", "TerraGroup实验室访问钥匙卡",
    "疗养院东楼 107 办公室钥匙", "疗养院东楼 205 房间钥匙", "疗养院东楼 306 房间钥匙",
    "疗养院东楼 308 房间钥匙", "疗养院东楼 310 房间钥匙", "疗养院东楼 328 房间钥匙",
    "疗养院西楼 104 办公室钥匙", "疗养院西楼 112 办公室钥匙", "疗养院西楼 203 房间钥匙",
    "疗养院西楼 216 房间钥匙", "疗养院西楼 218 房间钥匙", "疗养院西楼 219 房间钥匙",
    "疗养院西楼 220 房间钥匙", "疗养院西楼 306 房间钥匙",
    # 2026-10-18 追加：固定刷新的非钥匙高级物品（用户口径：只加这一件）
    'TerraGroup "蓝色文件夹" 材料',
)
HIGH_VALUE_SET = frozenset(HIGH_VALUE_ITEMS)


# --------------------------------------------------------------------------- #
# 人工校正表（上游数据有缺口或落后于游戏时的手工兜底，纯离线、可复现）
# --------------------------------------------------------------------------- #
# 上游对部分 Boss 刷新区只给了区域名、没给坐标（spawnLocations[].positions 为空），
# 前端拿不到点就画不出来，看起来像「少了一个刷新点」。这里用地图地名（config 里的
# labels，世界坐标）当锚点补齐：键是 (图 key, 上游区域名)，值是 (图例显示名, 地名文本)。
BOSS_ZONE_ANCHOR = {
    ("customs", "ZoneDormitory"): ("宿舍楼", "Dorms"),
    ("customs", "ZoneGasStation"): ("新加油站", "New Gas"),
    ("shoreline", "ZonePort"): ("码头", "Pier"),
}

# 上游整条记录都没有、但确实会刷 Boss 的补充点：键是图 key，值给出挂哪个 Boss、
# 显示名与取坐标的地名文本。
BOSS_SPOT_EXTRA = {
    "shoreline": [
        {"mob": "bossSanitar", "where": "加油站", "label": "Gas Station"},
    ],
}

# 已经过期的撤离点（游戏里删了、上游还留着）：键是 (图 key, 上游原始名)，精确剔除。
EXTRACT_EXCLUDE = {
    ("interchange", "Hole Exfill"),   # 围栏破洞：游戏里已移除
}

# 上游没给高度波段、但底图里确实有该层、且必须能单独判定的补充波段。
# 否则该层的标记会落到主层，界面上切到那一层会空无一物（点了没反应）。
# 键是图 key，值是若干 {svgLayer, label, minY, maxY, areas}。
# 海岸线：度假村有独立的一层（First_Floor）底图，但上游只登记了 2/3 层与地下层的高度区间，
# 一层没有波段——于是度假村一层（y 约 -2.7～-4）的每个房门/物资全被算进主层「地面层」，
# 切到「一层」时看不到任何标记（包括那些上锁的门）。这里按度假村轮廓补一个一层波段；
# 面积限定在度假村内，避免把别处低位（y 同样在 -5～-1）的地面标记误判成一层。
FLOOR_BAND_EXTRA = {
    "shoreline": [
        {"svgLayer": "First_Floor", "label": "一层", "minY": -5.0, "maxY": -1.0,
         "areas": [[-370.0, -200.0, -120.0, -20.0]]},
    ],
}


def container_slugs(markers_data):
    """从上游标注数据里取出「容器 id → slug」，容器类别要在 build_map 里按 slug 判定。"""
    defs = markers_data.get("lootContainers") or {}
    return {cid: (info or {}).get("normalizedName") for cid, info in defs.items()}


def build_map(entry, markers_by_name, translations, svg_viewbox, svg_layers=None, mobs=None,
              container_slug_map=None, item_translations=None, svg_name=None):
    """把单张图的配置 + 标注 + 翻译拼成前端要用的精简结构。

    ``item_translations`` 是物品中文名表，用来把锁的钥匙 id 解析成钥匙名。
    ``svg_name`` 是底图文件名（瓦片图是构建期拼出来的合成 SVG，上游 svgPath 里没有）。
    """
    container_slug_map = container_slug_map or {}
    item_translations = item_translations or {}
    key = entry["key"]
    marker_map = markers_by_name.get(key)
    if marker_map is None:
        raise ValueError("上游标注数据里找不到图 %s" % key)
    mobs = mobs or {}

    transform = entry.get("transform") or [1, 0, 1, 0]
    rotation = entry.get("coordinateRotation") or 0
    # 底图 SVG 铺满的矩形：上游给 svgBounds 时用它（如储备站，与瓦片的 bounds 不同），否则用 bounds
    svg_bounds = entry.get("svgBounds") or entry.get("bounds")
    if not svg_bounds:
        raise ValueError("图 %s 缺少 bounds，无法推导坐标变换" % key)

    world_to_svg = compute_world_to_svg(transform, rotation, svg_bounds, svg_viewbox)

    map_id = marker_map.get("id")
    name = localize(translations, "%s Name" % map_id, prettify_key(key))

    extracts = []
    for item in marker_map.get("extracts") or []:
        point = point_3d(item.get("position") or {})
        if point is None:
            continue
        raw_name = item.get("name") or ""
        if (key, raw_name) in EXTRACT_EXCLUDE:
            continue          # 上游还没跟上游戏的过期撤离点，直接跳过
        point["name"] = localize(translations, raw_name, raw_name)
        point["faction"] = item.get("faction") or "shared"
        extracts.append(point)

    transits = []
    for item in marker_map.get("transits") or []:
        point = point_3d(item.get("position") or {})
        if point is None:
            continue
        raw_desc = item.get("description") or ""
        point["name"] = localize(translations, raw_desc, raw_desc)
        transits.append(point)

    spawns = []
    for item in marker_map.get("spawns") or []:
        point = point_3d(item.get("position") or {})
        if point is None:
            continue
        point["sides"] = sorted(item.get("sides") or [])
        point["categories"] = sorted(item.get("categories") or [])
        spawns.append(point)

    # 雷区/狙击区等：上游带闭合多边形 outline，用来画危险区域而不是一个点
    hazards = []
    for item in marker_map.get("hazards") or []:
        point = point_3d(item.get("position") or {}, {"type": item.get("hazardType") or "hazard"})
        if point is None:
            continue
        outline = outline_2d(item.get("outline"))
        if outline:
            point["outline"] = outline
        hazards.append(point)

    # 钥匙门 / 后备箱：上游只给钥匙的物品 id，用物品中文名表换成钥匙名（拿不到就退回 id）
    locks = []
    for item in marker_map.get("locks") or []:
        key_id = item.get("key")
        point = point_3d(item.get("position") or {}, {
            "type": item.get("lockType") or "door",
            "needsPower": bool(item.get("needsPower")),
            "key": key_id,
        })
        if point is None:
            continue
        if key_id:
            key_name = localize(item_translations, "%s Name" % key_id, None)
            key_short = localize(item_translations, "%s ShortName" % key_id, None)
            if key_name:
                point["keyName"] = key_name
            if key_short:
                point["keyShort"] = key_short
        locks.append(point)

    # 物资容器：上游容器按 slug 归到 14 个类别（前端据此拆开关），译名走 "<id> Name"；
    # 查不到译名（如 Shturman 的藏匿点）就退回该类的中文名，免得详情里显示一串原始 ID
    containers = []
    for item in marker_map.get("lootContainers") or []:
        point = point_3d(item.get("position") or {})
        if point is None:
            continue
        raw_name = item.get("lootContainer") or ""
        group = container_group(container_slug_map.get(raw_name))
        point["name"] = localize(translations, "%s Name" % raw_name, CONTAINER_LABELS[group])
        point["group"] = group
        containers.append(point)

    loose = []
    for item in marker_map.get("lootLoose") or []:
        point = point_3d(item.get("position") or {})
        if point is not None:
            loose.append(point)

    # 高级资源点：散落刷点的物品池里含高价值物品的，单拎一层出来（BTC / 私酒 / LEDX / 除颤器 / 钥匙卡 / 稀有钥匙…）
    valuables = []
    for item in marker_map.get("lootLoose") or []:
        names: list[str] = []
        for item_id in item.get("items") or []:
            # 注意：这里的循环变量不能叫 name —— 上面 L321 的地图名同名，会被覆盖掉
            item_name = localize(item_translations, "%s Name" % item_id, None)
            if item_name in HIGH_VALUE_SET and item_name not in names:
                names.append(item_name)
        if not names:
            continue
        point = point_3d(item.get("position") or {}, {"items": names})
        if point is not None:
            valuables.append(point)

    # Boss 刷新点：把 spawnLocations[].positions[] 摊平成一个个点，带上 Boss 名与刷新概率。
    # 上游有部分刷新区只给区域名不给坐标（positions 为空），用 BOSS_ZONE_ANCHOR 借地名的世界
    # 坐标补一个点；上游整条记录都缺的（BOSS_SPOT_EXTRA）再手工追加。
    labels = []
    label_by_text = {}
    for item in entry.get("labels") or []:
        text = (item.get("text") or "").strip()
        x, z = flatten_positions(item.get("position"))
        if not text or x is None or z is None:
            continue
        labels.append({"text": text, "x": round(float(x), 3), "z": round(float(z), 3)})
        label_by_text[text] = (x, z)

    bosses = []
    for entry_item in marker_map.get("bosses") or []:
        mob_id = entry_item.get("mob") or ""
        mob_name = localize(translations, (mobs.get(mob_id) or {}).get("name") or mob_id, mob_id)
        chance = entry_item.get("spawnChance")
        for location in entry_item.get("spawnLocations") or []:
            positions = location.get("positions") or []
            if not positions and location.get("name"):
                # 只有区域名、没有坐标：用人工校正表的锚点地名补一个点
                anchor = BOSS_ZONE_ANCHOR.get((key, location["name"]))
                if anchor:
                    spot_x, spot_z = label_by_text.get(anchor[1], (None, None))
                    if spot_x is not None and spot_z is not None:
                        positions = [{"x": spot_x, "z": spot_z}]
                        location = {"name": anchor[0], "positions": positions}
            for position in positions:
                point = point_3d(position, {"name": mob_name})
                if point is None:
                    continue
                if location.get("name"):
                    point["where"] = location["name"]
                if chance is not None:
                    point["chance"] = round(float(chance), 3)
                bosses.append(point)

    spawn_chance_by_mob = {e.get("mob"): e.get("spawnChance") for e in marker_map.get("bosses") or []}
    for spot in BOSS_SPOT_EXTRA.get(key, []):
        spot_x, spot_z = label_by_text.get(spot["label"], (None, None))
        if spot_x is None or spot_z is None:
            continue
        mob_id = spot["mob"]
        mob_name = localize(translations, (mobs.get(mob_id) or {}).get("name") or mob_id, mob_id)
        chance = spawn_chance_by_mob.get(mob_id)
        bosses.append({
            "x": round(float(spot_x), 3), "z": round(float(spot_z), 3),
            "name": mob_name, "where": spot["where"],
            "chance": round(float(chance), 3) if chance is not None else 0.6,
        })

    # 炮击区（地图外沿的死亡区），同样是多边形
    artillery = []
    for zone in (marker_map.get("artillery") or {}).get("zones") or []:
        point = point_3d(zone.get("position") or {})
        if point is None:
            continue
        outline = outline_2d(zone.get("outline"))
        if outline:
            point["outline"] = outline
        artillery.append(point)

    btr = []
    for item in marker_map.get("btrStops") or []:
        raw_name = item.get("name") or ""
        point = point_3d(item, {"name": localize(translations, raw_name, "BTR 停靠点")})
        if point is not None:
            btr.append(point)

    # 固定武器（NSV 重机枪 / AGS 榴弹发射器这类架设武器）：上游只给武器 id，译名走 "<id> Name"
    stationary = []
    for item in marker_map.get("stationaryWeapons") or []:
        wid = item.get("stationaryWeapon") or ""
        point = point_3d(item.get("position") or {}, {
            "name": localize(translations, "%s Name" % wid, "固定武器"),
        })
        if point is not None:
            stationary.append(point)

    # 楼层结构：上游波段 + 本项目的补充波段（见 FLOOR_BAND_EXTRA）
    floors = build_floors(entry, svg_layers)
    for extra in FLOOR_BAND_EXTRA.get(key, []):
        floors["bands"].append(dict(extra))

    return {
        "key": key,
        "id": map_id,
        "name": name,
        "svg": "assets/maps/%s" % (svg_name or svg_basename(entry)),
        "viewBox": svg_viewbox,
        # 底图铺满的世界坐标矩形（供前端推算外边距，也供测试校验角点不变式）
        "svgBounds": [[float(svg_bounds[0][0]), float(svg_bounds[0][1])],
                      [float(svg_bounds[1][0]), float(svg_bounds[1][1])]],
        "svgLayer": entry.get("svgLayer"),
        # 底图 SVG 里实际存在的顶层图层：楼层能不能切，以此为准（上游有的层只有瓦片）
        "svgLayers": svg_layers or [],
        "floors": floors,
        "worldToSvg": {k: world_to_svg[k] for k in "abcdef"},
        "labels": labels,
        "layers": {
            "extracts": extracts,
            "transits": transits,
            "spawns": spawns,
            "hazards": hazards,
            "locks": locks,
            "containers": containers,
            "loose": loose,
            "valuables": valuables,
            "bosses": bosses,
            "artillery": artillery,
            "btr": btr,
            "stationary": stationary,
        },
    }


def write_atomic(path, data):
    """先写临时文件再原子替换，避免半截文件覆盖掉可用数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def source_entry(name, url, license_text, raw):
    return {
        "name": name,
        "url": url,
        "license": license_text,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def data_ready(selected_keys):
    """判断是否已有完整可用的产出（用于幂等跳过）。"""
    index = DATA_DIR / "maps.json"
    if not index.exists():
        return False
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 索引损坏就当作未就绪，走重新生成
        return False
    maps = payload.get("maps") or []
    if not maps:
        return False
    if payload.get("schema") != SCHEMA:
        return False                      # 老结构缺新图层，必须重新生成
    if selected_keys and {m.get("key") for m in maps} != set(selected_keys):
        return False
    return all((ROOT / m.get("svg", "")).exists() for m in maps)


def run(args):
    requested = [k.strip() for k in (args.maps or "").split(",") if k.strip()]

    if not args.force and data_ready(requested):
        print("[跳过] data/maps.json 与底图已就绪。要重新拉取请加 --force")
        return 0

    print("[1/4] 读取上游配置与翻译 …")
    config, config_raw = load_json_cached(
        MAP_CONFIG_URL, "tarkovdev-maps-config.json", force=args.force,
        timeout=TIMEOUT_SMALL, browser_ua=True,
    )
    markers, markers_raw = load_json_cached(
        MARKERS_URL.format(mode=args.mode), "markers-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_LARGE,
    )
    # 中文翻译同样优先走本地缓存：这样改分类逻辑后可以完全离线重跑生成 data/maps.json
    zh_cache = CACHE_DIR / ("maps_zh.json" if args.mode == "regular" else "maps_zh-%s.json" % args.mode)
    if zh_cache.exists() and not args.force:
        translations_raw = zh_cache.read_bytes()
    else:
        translations_raw = fetch(MARKERS_ZH_URL.format(mode=args.mode), timeout=TIMEOUT_LARGE)
        zh_cache.parent.mkdir(parents=True, exist_ok=True)
        zh_cache.write_bytes(translations_raw)
    translations = json.loads(translations_raw.decode("utf-8", "replace"))
    translations = translations.get("data", translations)

    # 物品中文名（只有钥匙这类物品用得上）：同样优先走本地缓存，改逻辑后可离线重跑
    items_cache = CACHE_DIR / ("items_zh.json" if args.mode == "regular" else "items_zh-%s.json" % args.mode)
    if items_cache.exists() and not args.force:
        items_raw = items_cache.read_bytes()
    else:
        items_raw = fetch(ITEMS_ZH_URL.format(mode=args.mode), timeout=TIMEOUT_LARGE)
        items_cache.parent.mkdir(parents=True, exist_ok=True)
        items_cache.write_bytes(items_raw)
    item_translations = json.loads(items_raw.decode("utf-8", "replace"))
    item_translations = item_translations.get("data", item_translations)
    print("      翻译表 %s 条，物品名 %s 条" % (len(translations), len(item_translations)))

    selected = select_maps(config, requested)
    markers_map = markers.get("data", markers)["maps"]
    markers_by_name = {m.get("normalizedName"): m for m in markers_map.values()}
    print("      配置文件 %s，标注 %s 张图，选中 %s 张" % (len(config), len(markers_map), len(selected)))

    print("[2/4] 准备底图（SVG 下载 / 瓦片拼接）…")
    viewboxes = {}
    svg_tops = {}
    svg_names = {}
    svg_bytes = 0
    tile_bytes_total = 0
    tile_map_count = 0
    for key, entry in selected.items():
        if key in TILE_MAPS:
            apply_tile_layer_ids(entry, key)          # 上游这些层没有 svgLayer，得先补上
            viewbox, tops, tile_bytes = build_tile_svg(key, entry, args.force)
            viewboxes[key] = viewbox
            svg_tops[key] = tops
            svg_names[key] = TILE_MAPS[key]["file"]
            svg_bytes += tile_bytes
            tile_bytes_total += tile_bytes
            tile_map_count += 1
            print("      %-18s %-38s 图层=%s" % (key, TILE_MAPS[key]["file"], tops))
            continue
        svg_name = svg_basename(entry)
        target = ASSETS_DIR / svg_name
        if target.exists() and not args.force:
            text = target.read_text(encoding="utf-8", errors="replace")
        else:
            raw = fetch(SVG_URL_TEMPLATE.format(name=svg_name[:-4]), browser_ua=True, timeout=TIMEOUT_LARGE)
            text = raw.decode("utf-8", "replace")
            write_atomic(target, raw)
        viewboxes[key] = parse_svg_viewbox(text)
        svg_tops[key] = parse_svg_top_layers(text)
        svg_names[key] = svg_name
        svg_bytes += target.stat().st_size if target.exists() else 0
        print("      %-18s %-38s 图层=%s" % (key, svg_name, svg_tops[key]))

    print("[3/4] 规范化标注数据 …")
    markers_data = markers.get("data", markers)
    mobs = markers_data.get("mobs") or {}
    slug_map = container_slugs(markers_data)
    maps = []
    for key in selected:
        item = build_map(selected[key], markers_by_name, translations, viewboxes[key],
                         svg_tops[key], mobs, slug_map, item_translations, svg_names[key])
        maps.append(item)
        counts = item["layers"]
        named_locks = sum(1 for lk in counts["locks"] if lk.get("keyName"))
        print(
            "      %-18s 撤离%3d 转移%2d 出生%3d 物资%4d/%3d 高价值%3d 雷区%3d 门%3d/钥匙名%3d boss%3d 固武%2d 层%2d/%2d"
            % (key, len(counts["extracts"]), len(counts["transits"]), len(counts["spawns"]),
               len(counts["containers"]), len(counts["loose"]), len(counts["valuables"]),
               len(counts["hazards"]), len(counts["locks"]), named_locks,
               len(counts["bosses"]), len(counts["stationary"]),
               len(item["floors"]["switchable"]), len(item["floors"]["bands"]))
        )

    print("[4/4] 写入 data/maps.json 与 data/meta.json …")
    sources = [
        source_entry("tarkov.dev 地图配置（the-hideout/tarkov-dev）", MAP_CONFIG_URL, "MIT", config_raw),
        source_entry("tarkov.dev 标注数据（json.tarkov.dev）", MARKERS_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", markers_raw),
        source_entry("tarkov.dev 中文翻译（json.tarkov.dev）", MARKERS_ZH_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", translations_raw),
        source_entry("tarkov.dev 中文物品名（json.tarkov.dev）", ITEMS_ZH_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", items_raw),
        source_entry("底图 SVG（the-hideout/tarkov-dev-svg-maps）", "https://assets.tarkov.dev/maps/svg/",
                     "CC BY-NC-SA 4.0（署名 + 非商业 + 同许可）", b""),
        # 实验室 / 迷宫上游只有瓦片：构建期按上游 transform + bounds 把瓦片拼成合成 SVG 底图
        source_entry("瓦片底图（tarkov.dev 地图瓦片，实验室 / 迷宫）", "https://assets.tarkov.dev/maps/",
                     "tarkov.dev 社区公开数据（署名 tarkov.dev，非商业）", b""),
    ]
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "schema": SCHEMA,
        "gameMode": args.mode,
        "generatedAt": generated_at,
        "sources": sources,
        "maps": maps,
    }
    meta = {
        "schema": SCHEMA,
        "generatedAt": generated_at,
        "gameMode": args.mode,
        "tool": "tools/fetch_data.py",
        "sources": sources,
        "counts": {
            "maps": len(maps),
            "extracts": sum(len(m["layers"]["extracts"]) for m in maps),
            "transits": sum(len(m["layers"]["transits"]) for m in maps),
            "spawns": sum(len(m["layers"]["spawns"]) for m in maps),
            "containers": sum(len(m["layers"]["containers"]) for m in maps),
            "loose": sum(len(m["layers"]["loose"]) for m in maps),
            "valuables": sum(len(m["layers"]["valuables"]) for m in maps),
            "hazards": sum(len(m["layers"]["hazards"]) for m in maps),
            "locks": sum(len(m["layers"]["locks"]) for m in maps),
            "bosses": sum(len(m["layers"]["bosses"]) for m in maps),
            "artillery": sum(len(m["layers"]["artillery"]) for m in maps),
            "btr": sum(len(m["layers"]["btr"]) for m in maps),
            "stationary": sum(len(m["layers"]["stationary"]) for m in maps),
            "locksNamed": sum(1 for m in maps for lk in m["layers"]["locks"] if lk.get("keyName")),
            "labels": sum(len(m["labels"]) for m in maps),
            "tileMaps": tile_map_count,
            "tileBytes": tile_bytes_total,
            "containerGroups": {
                key: sum(1 for m in maps for c in m["layers"]["containers"] if c.get("group") == key)
                for key, _label, _slugs in CONTAINER_GROUPS
            },
        },
    }
    write_atomic(DATA_DIR / "maps.json", json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"))
    write_atomic(DATA_DIR / "meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))

    print(
        "完成：%d 张图 / 底图 %.1f MB / 索引 %.0f KB（%s）"
        % (len(maps), svg_bytes / 1024 / 1024, (DATA_DIR / "maps.json").stat().st_size / 1024, args.mode)
    )
    print("署名：底图 SVG 为 CC BY-NC-SA 4.0，本项目非商业；详见 data/meta.json 与 README.md")
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description="拉取并规范化《逃离塔科夫》互动地图数据")
    parser.add_argument("--force", action="store_true", help="忽略已有产出与缓存，强制重新拉取")
    parser.add_argument("--maps", default="", help="逗号分隔的地图 key，默认拉取所有有 SVG 底图的图")
    parser.add_argument("--mode", default="regular", help="游戏模式：regular（默认）/ pve")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 - 顶层兜底：明确报错且不破坏已有数据
        print("[错误] %s" % exc, file=sys.stderr)
        print("已保留原有 data/ 与 assets/ 内容（本次未做破坏性写入）。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
