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
import gunpresets as gpresets        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "maps"
TILE_ASSET_DIR = ASSETS_DIR / "tiles"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "build-cache"
TILE_CACHE_DIR = CACHE_DIR / "tiles"

# 1 = M1（撤离/过境/出生/地名）；2 = 加入物资、危险区、钥匙门、Boss、楼层；
# 3 = 容器带类别；4 = 容器按参考站 14 类细分 + 新增「固定武器」图层；
# 5 = 锁带钥匙名（keyName） + 新增「高级资源点」图层（valuables）；
# 6 = 收录瓦片底图的实验室 / 迷宫（构建期把上游瓦片拼成合成 SVG 底图）；
# 7 = 高级资源点收录「显卡」（上游中文物品名是「显示卡」），需离线重跑一次生成 data/maps.json
# 8 = 高级资源点再收录「情报文件夹」（第十五轮：前端「其他高价值」子类拆成「情报」+「蓝色文件夹」两子类）
SCHEMA = 8

MARKERS_URL = "https://json.tarkov.dev/{mode}/maps"
MARKERS_ZH_URL = "https://json.tarkov.dev/{mode}/maps_zh"
# 物品中文名：上锁的门只给钥匙物品 id，要在这里换成「XX 房间钥匙」才看得懂
ITEMS_ZH_URL = "https://json.tarkov.dev/{mode}/items_zh"
MAP_CONFIG_URL = "https://raw.githubusercontent.com/the-hideout/tarkov-dev/main/src/data/maps.json"
SVG_URL_TEMPLATE = "https://assets.tarkov.dev/maps/svg/{name}.svg"

# 物品资料库（配装 / 配枪视图的数据源）：与 items_zh 同一个 host，17 MB 一份，构建期拉一次。
# 图标是 64px webp，约 2 KB/件，全量约 11 MB，随包分发（构建期下载，运行期纯本地）。
ITEMS_URL = "https://json.tarkov.dev/{mode}/items"
ITEM_ICON_URL = "https://assets.tarkov.dev/{id}-icon.webp"
# 商人 / 兑换配方 / 任务名（第五轮）：获取方式要显示「哪个商人 · 几级 · 购买还是兑换」，
# 上游 `items[].buyFromTrader` 只有商人 id，兑换配方在单独的 barters 里，任务解锁只有 id。
TRADERS_URL = "https://json.tarkov.dev/{mode}/traders"
TRADERS_ZH_URL = "https://json.tarkov.dev/{mode}/traders_zh"
BARTERS_URL = "https://json.tarkov.dev/{mode}/barters"
TASKS_URL = "https://json.tarkov.dev/{mode}/tasks"
# R27.0：藏身处制作（crafts）+ 设施表（hideout）——每条 craft 给出 产物 id / 设施 id / 设施等级 / 任务解锁
CRAFTS_URL = "https://json.tarkov.dev/{mode}/crafts"
HIDEOUT_URL = "https://json.tarkov.dev/{mode}/hideout"
HIDEOUT_ICON_URL = "https://assets.tarkov.dev/station-{name}.png"
ITEMS_SCHEMA = 6                 # data/items.json 的结构版本（与地图 SCHEMA 各自独立）
# 6：条目补 `sl`（上游 sellToTrader 卢布价，每个商人取最高、降序）与
#    `ci`（Preset 物品的 containsItems 配件清单），用于 Buy / Sell 与内置枪械预设还原。
# 2：补 `ts`（上游 types，根槽位归属的权威依据）、`aps`（护甲板槽位），
#    并让非配件类装备（护甲 / 头盔 / 胸挂 / 背包）也带 `slots`。
# 3：护甲槽区分「可装插板槽」与「固定内衬」（`fx:1`，保留上游真实防护数据）；
#    条目补 `mat`（材质）/ `at`（armorType）/ `z`（防护 zone）；顶层补 `materials`
#    （上游 armorMaterials 的毁损系数）、`categoryIds`（normalizedName → 分类 id）、
#    `audit`（七个一级类别的归属件数 / 重复归类 / 待审核清单）。
# 4：条目补 `src`（获取方式：flea / trader / barter / none / unknown，可多值共存）；
#    `audit.coverage` 补获取方式与减益字段覆盖率；顶层补 `audit.sources`（判定依据说明）。
# 5：条目补 `trade`（逐笔交易：商人 id / 等级 / 任务解锁 id / 价格与货币 / 兑换所需物品），
#    顶层补 `traders`（商人 id → 名称·头像·许可）与 `tasks`（任务 id → 英文名）。
#    购买与兑换用 `k` 明确区分（buy / barter），**不再只靠三个布尔 token 猜**。
ICON_WORKERS = 16                # 图标并发下载线程数
ICONS_DIR = ROOT / "assets" / "icons-items"
# 商人图标（第五轮）：**项目内自绘的中性图标**，不再从上游下载游戏角色美术。
# 许可复核结论（2026-10-20）：the-hideout/tarkov-dev 的 LICENSE 是 MIT，覆盖的是**源代码**；
# 该仓库 README 与基础设施文档均未给出图片素材的再分发许可，而 tarkov.dev 页面自己写明
# 「Game content and materials are trademarks and copyrights of Battlestate Games and its
# licensors. All rights reserved.」。因此 assets.tarkov.dev 上的商人头像**没有**明确的
# 可再分发许可，不能当作 MIT 或 CC BY-NC-SA 资源随包分发。改为自绘 {normalizedName}.svg
# （圆形底 + 商人缩写），商人名称、等级、交易类型与获取方式功能完全不变。
TRADER_ICONS_DIR = ROOT / "assets" / "icons-traders"
TRADER_PORTRAITS_DIR = TRADER_ICONS_DIR / "portraits"
# R23.2（用户 2026-10-30 决定）：商人头像改用**游戏素材**，与本项目既有的物品图标
# （assets/icons-items/*.webp，同样来自 assets.tarkov.dev）同源同口径。用途为学术研究、
# 非商用；自绘 SVG 保留为加载失败时的兜底，不再作为默认显示。
TRADER_PORTRAIT_URL = "https://assets.tarkov.dev/{id}.webp"
TRADER_PORTRAIT_LICENSE = "游戏素材（BSG 版权），学术研究/非商用；构建期下载，不随仓库再分发"
TRADER_ICON_LICENSE = "项目内自制，无第三方素材与再分发限制"
# 逐个记录来源（自绘）、许可与 SHA-256，落在 manifest 里可复核；`removed` 段保留本轮
# 下线的上游头像记录，便于审计「哪些文件曾经存在、为什么被移除」。
TRADER_ICON_MANIFEST = "manifest.json"
# 商人缩写：用**规范化英文名**做键，2–3 个字符，保证 32px 下可读且互不混淆。
TRADER_INITIALS = {
    "prapor": "PR", "therapist": "TH", "fence": "FE", "skier": "SK",
    "peacekeeper": "PK", "mechanic": "ME", "ragman": "RA", "jaeger": "JA",
    "lightkeeper": "LK", "btr-driver": "BTR", "ref": "REF", "mr-kerman": "KM",
    "voevoda": "VO", "taran": "TA", "radio-station": "RS", "survivor": "SV",
}
# 与商人图标放在同一目录、同样**不是**外部素材的两个本地自制图标：
#   flea    —— 跳蚤市场（这一渠道没有「商人」，必须有自己的图）；
#   unknown —— 来源未确认时的回退图（语义是「数据没给」，不是「不可获得」）。
TRADER_LOCAL_ICONS = {
    "flea": "跳蚤市场（项目内自绘，无外部素材）",
    "unknown": "来源未确认回退图（项目内自绘，无外部素材）",
}

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

# 破冰船的投影必须人工覆盖：上游这套 transform + bounds 不能直接用。
#   · transform [2.0, 125, 3.5, 91] 是**各向异性**的（x 缩放 2.0、z 缩放 3.5），
#     而其余 12 张图的 transform 全是各向同性；
#   · bounds [[77, -64.5], [-65.5, 67.4]] 与 factory 一字不差，明显是复制来的。
# 照它算，标记有 15.8% 掉在船体之外（出生点/「直升机」撤离被甩到船艏、船艉以外），
# 因为瓦片里的船图与标记的世界坐标根本不是一个口径。
#
# 自洽投影按「船体瓦片内容的像素跨度 ↔ 实体（出生/撤离/战利品）的世界跨度」反推：
#   · 船体内容在瓦片像素空间占 y[0, 256]（zoom3 的第 0..7 行，每行 32 px）；
#   · 实体 z 跨度 -78.3 ~ 82.3（跨度 160.6）→ 各向同性缩放 S = 256 / 160.6 ≈ 1.594 px/世界单位；
# x 取同一个 S（船体内容宽 64 px ÷ 1.594 ≈ 40 世界单位，与船长 160 的比例符合船型比例），
#   船体内容在像素上居中于 x=128 → 船中线世界 x ≈ 0.5（t1 = 128 + S * 0.5）。
# 验证：按这套投影把全部标记画到船图上叠加比对，出生点沿甲板合理分布、
# 「直升机」撤离点正落在船艏停机坪上（脚本与结论见 AGENT_HANDOFF.md §6.18）。
#
# 注意：瓦片下标仍按**上游画布**取（上面的数字只覆盖「世界 → 底图」映射与取景框），
# 由这套 transform + bounds 反推出的像素矩形是上游画布的子集，下标范围不会越界。
# bounds 由取景框精确反推（不手写四舍五入的常量），底图 viewBox 才能与索引逐位对齐。
_ICEBREAKER_SCALE = 256.0 / (82.3 + 78.3)
_ICEBREAKER_T1 = 128.8
_ICEBREAKER_T3 = _ICEBREAKER_SCALE * 78.3
_ICEBREAKER_TRANSFORM = [_ICEBREAKER_SCALE, _ICEBREAKER_T1, _ICEBREAKER_SCALE, _ICEBREAKER_T3]
# 取景框（瓦片像素）：船体内容 x[96,160] y[0,256] 四周各留 4 px，免得贴边的出生点被切
_FRAME_LEFT, _FRAME_TOP, _FRAME_RIGHT, _FRAME_BOTTOM = 92.0, -4.0, 164.0, 260.0
_ICEBREAKER_BOUNDS = [
    [(_ICEBREAKER_T1 - _FRAME_LEFT) / _ICEBREAKER_SCALE, (_FRAME_TOP - _ICEBREAKER_T3) / _ICEBREAKER_SCALE],
    [(_ICEBREAKER_T1 - _FRAME_RIGHT) / _ICEBREAKER_SCALE, (_FRAME_BOTTOM - _ICEBREAKER_T3) / _ICEBREAKER_SCALE],
]

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
    # 破冰船 16 层，每层一格瓦片目录、各自带高度带（可判定层）。
    # 与实验室不同：上游把「主层」entry.tilePath 直接指向了 show=true 的 Infirmary，
    # 若照搬 ``(None, …)`` 会与 Infirmary 那一层重复出两个内容相同的顶层组，
    # 所以这里**不用 None**，改用 rootLayer 显式指定主层。
    # 组 id 用 `Deck_序号` 前缀，让楼层列表按字符串排序就能得到自下而上的正确顺序。
    "icebreaker": {
        "file": "Icebreaker.svg",
        "rootLayer": "Deck_06_Infirmary",
        # 上游那套 transform / bounds 与船图对不上，改用上面反推的自洽投影
        "projection": {"transform": _ICEBREAKER_TRANSFORM, "bounds": _ICEBREAKER_BOUNDS},
        "layerIds": [
            ("Control Room", "Deck_00_Control_Room"),
            ("Engine Room", "Deck_01_Engine_Room"),
            ("Engine Room (upper)", "Deck_02_Engine_Room_Upper"),
            ("Fuel Pumps (lower)", "Deck_03_Fuel_Pumps_Lower"),
            ("Fuel Pumps", "Deck_04_Fuel_Pumps"),
            ("Storage/Security", "Deck_05_Storage_Security"),
            ("Infirmary", "Deck_06_Infirmary"),
            ("Helipad", "Deck_07_Helipad"),
            ("Gym/Canteen", "Deck_08_Gym_Canteen"),
            ("Accommodation (lower)", "Deck_09_Accommodation_Lower"),
            ("Accommodation (mid)", "Deck_10_Accommodation_Mid"),
            ("Accommodation (upper)", "Deck_11_Accommodation_Upper"),
            ("Officers' Deck", "Deck_12_Officers_Deck"),
            ("Stairs (blocked)", "Deck_13_Stairs_Blocked"),
            ("Bridge", "Deck_14_Bridge"),
            ("Bridge Roof", "Deck_15_Bridge_Roof"),
        ],
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
    root_layer = TILE_MAPS[key].get("rootLayer")
    if root_layer:
        # 上游把「主层」tilePath 指向了某个具名层时（破冰船 → Infirmary），显式指定主层，
        # 免得 layerIds 里再写一条 (None, …) 拼出两个内容重复的顶层组
        entry["svgLayer"] = root_layer


def apply_tile_projection(entry, key):
    """把 TILE_MAPS 里的人工投影覆盖到 entry 上（上游 transform / bounds 自相矛盾时用）。

    只覆盖「世界 → 底图」映射与取景框：瓦片下标由这套投影反推出的像素矩形决定，
    实测落在上游画布已有的下标范围内，不会多问不存在的格子（见 _ICEBREAKER_* 注释）。
    """
    projection = TILE_MAPS[key].get("projection")
    if not projection:
        return
    entry["transform"] = list(projection["transform"])
    entry["bounds"] = [list(pair) for pair in projection["bounds"]]
    entry.pop("svgBounds", None)     # 上游若补了 svgBounds，会盖掉我们刚覆盖的 bounds


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


# --------------------------------------------------------------------------- #
# 限时活动地图（2026-10-29 补丁 1.3.0.0「感染」事件，2026-11-15 上游仍在更新）
# --------------------------------------------------------------------------- #
# tarkov.dev 的 markers 端点里有 infected-lab / infected-factory（中文「实验室疫区」/
# 「工厂疫区」），但 the-hideout/tarkov-dev 的 GitHub 地图配置和 assets.tarkov.dev
# 都没有对应底图（实测各种命名均 404）。这两张图是实验室 / 工厂的活动变体：上游给出的
# 出生点与 Boss 坐标完全落在原图范围内（感染实验室 x[-279.7,-108.6] z[-423.3,-252.2]，
# 原实验室 x[-282.7,-110.1] z[-457.8,-218.9]；感染工厂同理），因此复用原图底图、
# transform 与 bounds 是安全的，只是标记换成活动图自己的 bosses / spawns。
# 构建期把 TheLab.svg / Factory.svg 各复制一份，再往 config 里注入只改了 key / svgPath
# 的派生条目，select_maps 就能照常收录，前端无需任何改动。
EVENT_MAP_ALIASES = (
    ("infected-lab", "the-lab", "InfectedLab.svg", "TheLab.svg"),
    ("infected-factory", "factory", "InfectedFactory.svg", "Factory.svg"),
)
EVENT_SVG_SOURCES = {new: base_svg for new, _base, _svg, base_svg in EVENT_MAP_ALIASES}


def with_event_maps(config):
    """给上游地图配置补两张活动图的派生条目（幂等；原图缺失时跳过，不阻断常规图）。"""
    entries = {}
    for group in config:
        for entry in group.get("maps") or []:
            if isinstance(entry, dict) and entry.get("key"):
                entries[entry["key"]] = entry
    existing = set(entries)
    added = []
    for new_key, base_key, svg_name, _base_svg in EVENT_MAP_ALIASES:
        if new_key in existing or base_key not in entries:
            continue
        entry = dict(entries[base_key])
        entry["key"] = new_key
        entry["svgPath"] = SVG_URL_TEMPLATE.format(name=svg_name[:-4])
        # 原实验室是瓦片图：派生条目改走普通 SVG 路径，别把 tilePath / altMaps 带过来
        entry.pop("tilePath", None)
        entry.pop("altMaps", None)
        # 瓦片图的主层 svgLayer 平时由 apply_tile_layer_ids() 在 run() 里补上，
        # 派生条目不走那条路径；不补会让 floors.root.svgLayer 为 None（前端切层失效）。
        if not entry.get("svgLayer") and base_key in TILE_MAPS:
            entry["svgLayer"] = TILE_MAPS[base_key]["layerIds"][0][1]
        added.append(entry)
    if not added:
        return config
    return list(config) + [{"normalizedName": "event-maps", "primaryPath": "", "maps": added}]


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
    # 2026-10-19 追加：显卡（游戏里叫「显卡」，上游物品名是「显示卡」）——单独一类，价值高且刷点密
    "显示卡",
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
    # 2026-10-18 追加：非钥匙的高级物品
    'TerraGroup "蓝色文件夹" 材料',
    # 2026-10-19 第十五轮追加：情报文件夹（上游物品名就是「情报文件夹」，id 5c12613b86f7743bbe2c3f76）。
    # 该物品不是固定刷新（物品池大多 >1），但刷点多、玩家认可度高，单列一个子类。
    "情报文件夹",
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

# 上游坐标标错的刷新区：这些区域**上游是给了 positions 的**，但坐标落在别处，必须整段换掉。
# 优先级高于 BOSS_ZONE_ANCHOR（后者只兜「positions 为空」）。键是 (图 key, 上游区域名)，
# 值是 (图例显示名, 地名文本)。
# 海岸线：ZoneMeteoStation（气象站）上游给了 10 个坐标，实测却分散在村庄（8 个）与无线电塔
# 一带（2 个）；游戏里三狗（Knight / Big Pipe / Bird Eye）现在只在气象站刷新，按玩家反馈
# 改为锚定地图地名「Weather Station」（护卫与 Knight 共用同一刷新区，跟着一起挪）。
BOSS_ZONE_FORCE = {
    ("shoreline", "ZoneMeteoStation"): ("气象站", "Weather Station"),
}

# 已经过期的撤离点（游戏里删了、上游还留着）：键是 (图 key, 上游原始名)，精确剔除。
EXTRACT_EXCLUDE = {
    ("interchange", "Hole Exfill"),   # 围栏破洞：游戏里已移除
}

# 上游把位置 / 轮廓画错的危险区：键是 (图 key, 上游给的 x, z)，值是修正后的完整条目。
# 塔科夫街区那片狙击区（不打绿色信号弹进去就会被打）实际盖在街区西北角，上游却标在
# x -40～-103 / z -34～35 一带；这里连中心点一起按游戏内实际轮廓修正。
# 狙击区是整片「垂直到底」的区域，没有高度含义，所以修正值里**不给 y**（前端据此不做
# 楼层过滤，详情里也不会显示 y）。
HAZARD_FIXES = {
    ("streets-of-tarkov", -71.9, 0.6): {
        "x": -232.49, "z": 38.8, "type": "sniper",
        "outline": [[-203.0, 0.0], [-273.0, 12.0], [-262.0, 79.0], [-192.0, 67.0]],
    },
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


def apply_hazard_fix(map_key, point):
    """把上游画错的危险区换成 ``HAZARD_FIXES`` 里的修正值；匹配不上就原样返回。

    按 ``(图 key, 上游 x, 上游 z)`` 精确匹配（坐标已在 ``point_3d`` 里取整到 3 位小数）。
    """
    fix = HAZARD_FIXES.get((map_key, round(point["x"], 3), round(point["z"], 3)))
    if not fix:
        return point
    out = {"x": fix["x"], "z": fix["z"], "type": fix.get("type") or point.get("type")}
    if "y" in fix:
        out["y"] = fix["y"]
    if fix.get("outline"):
        out["outline"] = [[float(px), float(pz)] for px, pz in fix["outline"]]
    return out


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
        hazards.append(apply_hazard_fix(key, point))

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
    # 坐标补一个点；坐标标错的（BOSS_ZONE_FORCE）整段换掉；上游整条记录都缺的
    # （BOSS_SPOT_EXTRA）再手工追加。
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
            zone_name = location.get("name")
            anchor = None
            if zone_name and (key, zone_name) in BOSS_ZONE_FORCE:
                # 上游给了坐标但标错了：无条件换成人工校正表里的地名锚点
                anchor = BOSS_ZONE_FORCE[(key, zone_name)]
            elif not positions and zone_name:
                # 只有区域名、没有坐标：用人工校正表的锚点地名补一个点
                anchor = BOSS_ZONE_ANCHOR.get((key, zone_name))
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


# --------------------------------------------------------------------------- #
# 物品资料库（配装 / 配枪视图的数据源）
# --------------------------------------------------------------------------- #
# 6 个配装槽位与上游 `propertiesType` 的对应关系。护面（面罩 / 护耳）走
# `ItemPropertiesArmorAttachment`——上游把头盔附件（面罩、护耳、侧甲板）都归在这一类。
GEAR_SLOT_TYPES = {
    "ItemPropertiesHelmet": "helmet",
    "ItemPropertiesArmorAttachment": "face",
    "ItemPropertiesGlasses": "glasses",
    "ItemPropertiesArmor": "armor",
    "ItemPropertiesChestRig": "rig",
    "ItemPropertiesBackpack": "backpack",
}

_UNSET = object()


def _zh_name(zh, item_id, item):
    """中文名：优先 `items_zh` 的 `<id> Name`，缺失时回落短名 / 规范化名。"""
    name = zh.get("%s Name" % item_id) if isinstance(zh, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    for key in ("shortName", "normalizedName", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return item_id


def _zh_short_name(zh, item_id, item):
    """R300：游戏内缩写（如 6B43 / PACA / ULACH / 帽）。

    上游 `shortName` 是本地化键（形如 `<id> ShortName`），中文名表里正好有对应值；
    取不到时回落到原始 shortName（仍不是键时），最后再退回空串（由上层层级兜底）。
    """
    raw = item.get("shortName")
    if isinstance(zh, dict) and isinstance(raw, str):
        value = zh.get(raw)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return raw.strip() if isinstance(raw, str) and raw.strip() else ""


def _slot_label(zh, slot):
    """槽位中文标签：`name` / `nameId` 大写后去 `items_zh` 里查（如 MOD_PISTOL_GRIP → 手枪式握把）。"""
    for key in (slot.get("name"), slot.get("nameId")):
        if isinstance(key, str) and key:
            label = zh.get(key.upper()) if isinstance(zh, dict) else None
            if isinstance(label, str) and label.strip():
                return label.strip()
    return slot.get("name") or slot.get("nameId") or ""


def _compact(mapping):
    """丢掉值为 0 / None / 空容器的键，压体积（0 是合法数值但这里按「无意义」处理）。"""
    out = {}
    for key, value in mapping.items():
        if value in (None, 0, 0.0, "", [], {}):
            continue
        out[key] = value
    return out


def _market_fields(item: dict) -> dict:
    """上游现成的市场指标，压到 `mk` 块：涨跌 / 在售挂单数 / 最近扫描时间。

    R286 市场大盘：字段直接来自 `json.tarkov.dev` 的 items 数据集，均为上游原值。
    `o` = lastOfferCount 是**当前在售挂单数**，不是成交笔数——上游无成交量字段，
    UI 必须标注为「在售挂单数」，不得当作成交量展示。
    0 是合法值（涨跌幅为 0 / 当前无挂单），因此这里不能用 `_compact()` 丢零。
    """
    out: dict = {}
    for src, dst in (("changeLast48hPercent", "c"), ("changeLast48h", "d"),
                     ("velocity", "v"), ("lastOfferCount", "o"), ("lastScan", "s")):
        value = item.get(src)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float, str)) and value != "":
            out[dst] = value
    return out


# ------------------------------------------------------------------ 槽位数据修正
# 上游数据与**游戏内实测**不一致时的显式修正表。只收录已确证的条目，
# 不按类别推断其他物品（其他瞄具/底座必须逐一核实后单独加条目）。
OPTIC_SLOT_CORRECTIONS = {
    # Nightforce MagMount Multimount 34mm 一体式导轨基座
    # 证据：游戏内实测（2026-10-26 用户确认）直接槽位恰好 2 个：
    #   1) 34mm 光学瞄准镜槽；2) 单倍瞄具 / 单倍瞄具底座槽。
    # 上游快照声明 4 个同名 MOD_SCOPE：
    #   _000 = 4 件 34mm 光学瞄具              → 34mm 光学槽（保留）
    #   _001 = 1 倍瞄具 + 战术测距仪 + 5 个微型底座 → 单倍瞄具/底座槽（保留）
    #   _002/_003 = 与 _001 子集完全相同、且两者互相重复的底座列表 → 游戏中不存在的重复节点（移除）
    "5aa66c72e5b5b00016327c93": {
        "evidence": "in-game-confirmed",
        "keep": ["5aa66c90e5b5b00016327c96", "5aa66c9ce5b5b00015693125"],
        "drop": ["5aa66cabe5b5b055d0630d82", "5aa66cb7e5b5b0214e506e99"],
        "labels": {"5aa66c9ce5b5b00015693125": "单倍瞄具 / 单倍瞄具底座"},
    },
}


try:                                     # R19.18：真实槽位修正表（与当前 data/ 同源）
    import slotfix
except Exception:                        # pragma: no cover - 独立运行时退回无修正
    slotfix = None


def _apply_slot_correction(out, item_id):
    """按 OPTIC_SLOT_CORRECTIONS / R1918_ITEM_SLOT_FIXES 修正某物品的直接槽位。

    只改直接槽位列表（不递归子件），两种修正互不冲突：先按 OPTIC 表做保留/改名，
    再按 R19.18 表删除「游戏里不存在 / 重复」的槽位。
    """
    fix = OPTIC_SLOT_CORRECTIONS.get(item_id or "")
    if fix:
        out = _apply_optic_correction(out, fix)
    # R19.18 / R19.19：真实槽位修正（删掉上游多出来的槽位，证据见 tools/slotfix.py）
    if slotfix is not None:
        for table in (getattr(slotfix, "R1918_ITEM_SLOT_FIXES", {}),
                      getattr(slotfix, "R1919_ITEM_SLOT_FIXES", {}),
                      getattr(slotfix, "R1921_ITEM_SLOT_FIXES", {})):
            fix = table.get(item_id or "")
            if not fix:
                continue
            drop = set(fix.get("drop") or [])
            if drop:
                out = [s for s in out if s.get("id") not in drop]
            for s in out:
                s["fix"] = fix.get("evidence")
    return out


def _apply_optic_correction(out, fix):
    """按 OPTIC_SLOT_CORRECTIONS 修正某物品的直接槽位（只改直接槽位列表）。"""
    keep = fix.get("keep")
    if keep:
        kept = [s for s in out if s.get("id") in keep]
        # 顺序按 keep 声明，保证 34mm 槽在前、单倍槽在后
        kept.sort(key=lambda s: keep.index(s.get("id")) if s.get("id") in keep else 99)
        out = kept
    labels = fix.get("labels") or {}
    for s in out:
        if s.get("id") in labels:
            s["label"] = labels[s["id"]]
    for s in out:
        s["fix"] = fix.get("evidence")
    return out


def _item_slots(props, zh, item_id=None):
    """把枪 / 配件的槽位树压成紧凑形式：`[id, sid, 标签, 是否必需, 允许物品, 允许分类]`。

    `sid` = 上游 `nameId`（如 `mod_nvg` / `mod_equipment_000`）。**必须保留**：`label` 是
    翻译表的结果，`mod_equipment` 与 `mod_equipment_000/001/002` 会被译成同一个「装备」，
    光靠 label 分不出槽位种类。
    """
    out = []
    for slot in props.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        filters = slot.get("filters") or {}
        out.append(_compact({
            "id": slot.get("id"),
            "sid": slot.get("nameId"),
            "label": _slot_label(zh, slot),
            "required": bool(slot.get("required")),
            "allow": list(filters.get("allowedItems") or []),
            "cats": list(filters.get("allowedCategories") or []),
        }))
    out = _apply_slot_correction(out, item_id)
    # R19.19：AKMP RS 等价迁移（并入枪身唯一照门槽 allow）——items.json 与
    # gunslots.json 的 allow 必须一致，gun_builder.buildTree 读的是 items.json。
    if slotfix is not None and hasattr(slotfix, "apply_gun_slot_allow_adds"):
        slotfix.apply_gun_slot_allow_adds(
            {item_id: {"slots": out}}, getattr(slotfix, "R1919_GUN_SLOT_ALLOW_ADDS", {}))
    return out


def _compact_keep_zero(mapping):
    """同 `_compact`，但保留 0。

    护甲等级 / 耐久 / 毁损系数里 0 是合法数值（如 `class: 0` 的软甲），
    不能被当成「无意义」丢掉，否则前端只能显示「—」，与「数据缺失」混淆。
    """
    out = {}
    for key, value in mapping.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        out[key] = value
    return out


_ZONE_PREFIXES = ("Collider Type ", "Armor Zone ")


def _zone_key(zone):
    """上游 zone 字符串去掉前缀：`Collider Type RibcageUp` → `RibcageUp`；
    `Armor Zone Plate_Granit_SAPI_chest` → `Plate_Granit_SAPI_chest`。"""
    text = zone if isinstance(zone, str) else ""
    for prefix in _ZONE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _zones(raw_zones):
    return [_zone_key(z) for z in (raw_zones or []) if isinstance(z, str)]


def _insert_zone_before_cats(rec, zones):
    """把 `z` 插到 `cats` 之前（与 `build_items` 的字段顺序一致）。

    `build_items` 生成的 `z` 位于 `cats` 之前，但空值会被 `_compact()` 丢弃；
    兜底若直接 `rec["z"] = …` 会追加到记录末尾，重建出的字节顺序与基线不同，
    SHA-256 永远对不上。显式重建字典，保证顺序确定（与
    `tools/r79_apply_zone_fallback.py` 的 `insert_zone` 同口径）。
    """
    out = {}
    placed = False
    for key, value in rec.items():
        if key == "z":
            continue                      # 旧值（空）不保留，统一在 cats 前重插
        if key == "cats" and not placed:
            out["z"] = zones
            placed = True
        out[key] = value
    if not placed:
        out["z"] = zones
    return out


def apply_truth_zone_fallback(payload):
    """R79：上游对眼镜 / 部分面具不返回 `properties.zones`，用 game-truth 补齐。

    `data/game-truth/armor_items.json` 是游戏文件提取结果，`props.armorColliders`
    才是权威防护区（例如 6B34 护目镜 = `["Eyes"]`）。只补 `z` 为空的物品，
    已有值一律不动；game-truth 不存在时静默跳过（离线构建不因缺文件失败）。
    结果完全确定：遍历顺序取自上游 items 的固有顺序，取值来自固定文件，
    `z` 去重后按 colliders 原序输出，并插在 `cats` 之前 —— 同一输入必得同一字节，
    meta 里的 sha256 才能长期稳定。
    返回补齐件数，供构建日志输出。
    """
    path = DATA_DIR / "game-truth" / "armor_items.json"
    try:
        with open(path, encoding="utf-8") as f:
            truth = json.load(f)
    except (OSError, ValueError):
        return 0
    truth_items = truth.get("items") if isinstance(truth, dict) else None
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(truth_items, dict) or not isinstance(items, dict):
        return 0
    filled = 0
    for iid, rec in items.items():
        if not isinstance(rec, dict) or rec.get("z"):
            continue
        props = (truth_items.get(iid) or {}).get("props") or {}
        colliders = [c for c in (props.get("armorColliders") or [])
                     if isinstance(c, str) and c]
        if not colliders:
            continue                          # 保持上游顺序，再去重，结果确定
        items[iid] = _insert_zone_before_cats(rec, list(dict.fromkeys(_zones(colliders))))
        filled += 1
    return filled


def _item_armor_slots(props):
    """`armorSlots` 压成两种条目（实测 306 条可装板槽 + 702 条固定内衬）：

    - 有 `allowedPlates` → **可装插板的槽**：`{zone, plates[], z[]}`，由玩家选装；
    - 无 `allowedPlates` → **固定内衬**：`{zone, fx:1, mat, cl, dur, at, z[], bt, bv}`。
      内衬是装备的固定结构（不可拆卸 / 不可替换），但**有真实数据**。
      第一轮只存 `{zone, plates:[]}` 把材质 / 等级 / 耐久 / 防护区全丢了，
      前端只能显示「数据缺失」——那是提取缺陷，不是上游缺口。
    """
    out = []
    for slot in props.get("armorSlots") or []:
        if not isinstance(slot, dict):
            continue
        zone = _zone_key(slot.get("nameId"))
        zones = _zones(slot.get("zones"))
        plates = list(slot.get("allowedPlates") or [])
        if plates:
            out.append(_compact_keep_zero({"zone": zone, "plates": plates, "z": zones}))
        else:
            out.append(_compact_keep_zero({
                "zone": zone, "fx": 1,
                "mat": slot.get("armorMaterial"), "cl": slot.get("class"),
                "dur": slot.get("durability"), "at": slot.get("armorType"),
                "z": zones, "bt": slot.get("bluntThroughput"),
                "bv": slot.get("baseValue"),
            }))
    return out


def _grid_limits(props):
    """容器（背包 / 胸挂）的**物品级**装载限制，压成 `{a: [id…], e: [id…]}`。

    - `a`（Allowed Only 仅允许）：上游 `grids[].filters.allowedItems` 的白名单并集；
    - `e`（Excluded 排除）：`grids[].filters.excludedItems` 的黑名单并集。
    只取**具体物品**限制；分类级限制（allowedCategories / excludedCategories）不外露——
    实测背包 / 胸挂几乎都挂了通用分类「物品」，把它显示成「仅允许：物品」只是噪声，
    参考图里那些格子也是空的，所以**不臆造**成有内容的限制。
    """
    allow, exclude = [], []
    for grid in (props.get("grids") or []):
        if not isinstance(grid, dict):
            continue
        filt = grid.get("filters")
        if not isinstance(filt, dict):
            continue
        for key, bucket in (("allowedItems", allow), ("excludedItems", exclude)):
            for iid in (filt.get(key) or []):
                if isinstance(iid, str) and iid and iid not in bucket:
                    bucket.append(iid)
    out = {}
    if allow:
        out["a"] = allow
    if exclude:
        out["e"] = exclude
    return out


HEADPHONE_FIELDS = ("distanceModifier", "ambientVolume", "dryVolume", "distortion",
                    "compressorGain", "compressorThreshold")


def _headphone_props(props):
    """耳机参数（参考图 Distance / Ambient / Dry Volume / Resonance 四列的真实来源）。

    上游 `ItemPropertiesHeadphone` 实测字段：`distanceModifier` / `ambientVolume` /
    `dryVolume` / `distortion` / `compressor*`。键名做缩写：`d` 距离系数、`a` 环境音量、
    `dv` 干音量、`r` 失真（参考图里那一列叫 Resonance）、`g` 压缩增益、`gt` 压缩阈值。
    取不到的字段留空，前端显示「—」，**不用 0 顶替**。
    """
    if not any(props.get(f) is not None for f in HEADPHONE_FIELDS):
        return None
    return _compact_keep_zero({
        "d": props.get("distanceModifier"), "a": props.get("ambientVolume"),
        "dv": props.get("dryVolume"), "r": props.get("distortion"),
        "g": props.get("compressorGain"), "gt": props.get("compressorThreshold"),
    })


def _armor_materials(raw_data):
    """上游 `armorMaterials` → `{材质名: {d: 毁损系数, ed: 爆炸毁损系数}}`（8 条全量）。

    有效耐久 = 基础耐久 ÷ 毁损系数，所以毁损系数必须落库，不能在前端猜。
    """
    out = {}
    for name, entry in ((raw_data or {}).get("armorMaterials") or {}).items():
        if not isinstance(entry, dict):
            continue
        out[name] = _compact_keep_zero({"d": entry.get("destructibility"),
                                        "ed": entry.get("explosionDestructibility")})
    return out


def _category_ids(raw_data):
    """上游 `itemCategories` → `{normalizedName: id}`（112 条）。

    本地分类纠错以这批**稳定分类 id** 为依据：`face-cover` / `vis-observ-device` /
    `headwear` / `armor-plate` / `armor` / `rig` / `backpack` / `headphones` 等。
    上游没有 `faceCover` / `eyewear` 这种 type，只有分类树，所以必须把分类 id 落库。
    """
    out = {}
    for cid, cat in ((raw_data or {}).get("itemCategories") or {}).items():
        if not isinstance(cat, dict):
            continue
        key = cat.get("normalizedName")
        if isinstance(key, str) and key:
            out[key] = cid
    return out


CATEGORY_LABELS = {
    "armor": "护甲", "helmet": "头盔", "headphones": "耳机", "backpack": "背包",
    "rig": "胸挂", "glasses": "眼镜", "face": "护面", "plate": "护甲板",
}

# 七个**一级**类别（护甲板不算一级，只作护甲插板子槽的候选）。
ROOT_CATEGORY_KEYS = ("helmet", "headphones", "glasses", "face", "armor", "rig", "backpack")

# 「获取方式」（第六项）的判定标记与中文标签：构建期算好写进 items[].src，运行期只做查表。
ACCESS_KEYS = ("flea", "trader", "barter")
# 逐笔交易的来源类型（第五轮）：flea = 跳蚤市场；buy = 商人货币购买；barter = 商人兑换。
# **购买与兑换是不同交易类型**，各自成条，不合并。
TRADE_KINDS = ("flea", "buy", "barter")
ACCESS_LABELS = {
    "flea": "跳蚤市场购买",
    "trader": "商人购买",
    "barter": "商人兑换",
    "none": "以上方式不可获得",
    "unknown": "数据未确认",
}

# 上游只有分类树（itemCategories），没有 faceCover / eyewear 这类 type，所以护面与眼镜
# 必须靠分类 id 判定；这里把判定依据写死，供审计表与前端共同引用。
CATEGORY_RULES = {
    "helmet": "items[].types 含 helmet；换色/皮肤版头盔与帽子按 headwear 分类补齐"
              "（头戴基座这类带 mod_nvg 子槽的配件除外）",
    "armor": "items[].types 含 armor",
    "plate": "items[].types 含 armorPlate（仅作护甲插板子槽候选，不占一级类别）",
    "glasses": "items[].types 含 glasses 且 items[].categories 含 vis-observ-device 分类",
    "face": "items[].categories 含 face-cover 分类",
    "rig": "items[].types 含 rig",
    "backpack": "items[].types 含 backpack",
    "headphones": "items[].types 含 headphones",
}

# `_classify_matches` 的判定顺序 = 优先级：先到先得 → 天然互斥（不会在多个一级类别里重复列出）。
CATEGORY_RULE_ORDER = ("helmet", "armor", "plate", "glasses", "face", "rig", "backpack", "headphones")

GEAR_PROPERTY_TYPES = frozenset(GEAR_SLOT_TYPES)


def _classify_matches(item, category_ids):
    """列出该物品命中的**全部**类别规则（按优先级排序）。

    优先级（先命中者为准）：头盔 > 护甲 > 护甲板 > 眼镜 > 护面 > 胸挂 > 背包 > 耳机。

    实测依据（`build-cache/items-regular.json`）：
    - 23 件护甲同时 `types` 含 armor 与 rig → 归**护甲**，不在胸挂里重复；
    - 3 件 Tagilla 电焊面罩 `types` 含 helmet 且在 face-cover 分类里 → 归**头盔**，护面不重复；
    - `types` 含 glasses 共 54 件，其中 14 件是挂在父头盔 `slots[].allowedItems` 上的
      面罩 / 护目罩，只有带 `vis-observ-device` 分类的 40 件才是独立眼部装备。
    """
    types = {t for t in (item.get("types") or []) if isinstance(t, str)}
    cats = {c for c in (item.get("categories") or []) if isinstance(c, str)}
    props = item.get("properties")
    props = props if isinstance(props, dict) else {}
    ptype = props.get("propertiesType") or ""
    vis_id = category_ids.get("vis-observ-device")
    face_id = category_ids.get("face-cover")
    headwear_id = category_ids.get("headwear")
    # 换色 / 皮肤版头盔（以及帽子）在上游没有 types=helmet，但都挂在 headwear 分类树里；
    # 只补这一条分类依据，避免「同一顶头盔只有原版能选、换色版全部消失」。
    # Headwear 里带子槽的是头戴基座（mod_nvg）等头盔配件，不占头戴槽，排除。
    helmet_by_category = bool(
        headwear_id and headwear_id in cats and (
            ptype == "ItemPropertiesHelmet"
            or (ptype == "ItemPropertiesHeadwear" and not (props.get("slots") or []))
        )
    )
    out = []
    if "helmet" in types or helmet_by_category:
        out.append("helmet")
    if "armor" in types:
        out.append("armor")
    if "armorPlate" in types:
        out.append("plate")
    if vis_id and vis_id in cats and "glasses" in types:
        out.append("glasses")
    if face_id and face_id in cats:
        out.append("face")
    if "rig" in types:
        out.append("rig")
    if "backpack" in types:
        out.append("backpack")
    if "headphones" in types:
        out.append("headphones")
    out.sort(key=CATEGORY_RULE_ORDER.index)
    return out


def _classify_item(item, category_ids):
    """一级类别归属：返回 (key | None, 命中的全部 key)。"""
    matches = _classify_matches(item, category_ids)
    return (matches[0] if matches else None), matches


def _has_currency_offer(buy_from_trader) -> bool:
    """`buyFromTrader` 里是否至少有一条**用货币购买**的报价（RUB / USD / EUR）。

    实测上游 2613 件有该字段，报价的 `currency` 只出现 RUB / USD / EUR 三种，
    且每条都带 `priceRUB`——即全部是货币购买，没有「物品交换型」报价（`buyFor` 为 0）。
    """
    if not isinstance(buy_from_trader, list):
        return False
    for offer in buy_from_trader:
        if not isinstance(offer, dict):
            continue
        if offer.get("price") is not None or offer.get("priceRUB") is not None:
            return True
    return False


def _access_sources(types, buy_from_trader) -> list:
    """由上游 `types` 与 `buyFromTrader` 推出「获取方式」（**多种方式可共存，全部保留**）。

    判定规则（构建期算好、随 `data/items.json` 打包，运行期**不联网**）：

    - `flea`（跳蚤市场购买）：允许上跳蚤 —— 上游 `types` **不含** `noFlea`；
    - `trader`（商人购买）：`buyFromTrader` 里有用货币直接购买的报价（RUB / USD / EUR）；
    - `barter`（商人兑换）：上游 `types` **含** `barter`（需消耗其它物品交换）；
    - `none`（以上方式不可获得）：来源数据完整，但上面三种一个都没有；
    - `unknown`（数据未确认）：来源数据缺失 / 无法判断 —— **不把未知误判成「不可获得」**。

    注：上游 `regular` 数据集是单一模式（没有 PVP / PVE 两套来源），所以不做模式拆分。
    """
    if not isinstance(types, list) or not types:
        return ["unknown"]
    tset = {t for t in types if isinstance(t, str)}
    out = []
    if "noFlea" not in tset:
        out.append("flea")
    if _has_currency_offer(buy_from_trader):
        out.append("trader")
    if "barter" in tset:
        out.append("barter")
    return out or ["none"]


# --------------------------------------------------------------------------- #
# 商人 / 兑换配方 / 任务名（第五轮：获取方式图标化的数据基础）
# --------------------------------------------------------------------------- #
def _trader_table(traders_data, traders_zh):
    """商人 id → `{nn: 规范化英文名, n: 显示名}`。

    显示名优先取 `traders_zh` 的 `<id> Nickname`。上游对几位主商人给的正是
    `Prapor` / `Therapist` / `Ragman` 这种社区通用写法（与参考站一致），**不自行改写**。
    """
    out = {}
    for tid, trader in (traders_data or {}).items():
        if not isinstance(trader, dict):
            continue
        nn = trader.get("normalizedName") or ""
        nick = (traders_zh or {}).get("%s Nickname" % tid) if isinstance(traders_zh, dict) else None
        name = nick.strip() if isinstance(nick, str) and nick.strip() else (nn or tid)
        out[tid] = _compact({"nn": nn or None, "n": name})
    return out


def _task_table(tasks_data):
    """任务 id → 任务名。

    上游 `tasks[].name` **全是 `<id> name` 这种占位串**（实测 503 个任务无一例外），
    中文名也不在 translations 里。可用的真实字段只有 `wikiLink`，所以退化用它：
    取 `/wiki/<slug>` 的 slug、下划线换空格（如 `First_in_Line` → `First in Line`）。
    这不是猜——是对上游字段的直接变换，规则写在 `audit.sources.trade.taskUnlock` 里；
    取不到 wikiLink 的任务**不进表**，界面显示「任务名未确认」而不是编一个名字。
    """
    out = {}
    for tid, task in (tasks_data or {}).items():
        if not isinstance(task, dict):
            continue
        name = task.get("name")
        if isinstance(name, str) and name.strip() and not name.strip().endswith(" name"):
            out[tid] = name.strip()
            continue
        wiki = task.get("wikiLink")
        if isinstance(wiki, str) and "/wiki/" in wiki:
            slug = wiki.rsplit("/wiki/", 1)[1].split("#")[0].split("/")[0]
            slug = slug.replace("_", " ").strip()
            if slug:
                out[tid] = slug
    return out


def _barter_index(barters_data):
    """兑换配方按**产出物品 id** 建索引：`{item_id: [barter, …]}`。

    上游一条 barter = `{trader, minTraderLevel, taskUnlock, requiredItems[{item,count}],
    offeredItem{item,count}}`。
    """
    index: dict = {}
    for rec in (barters_data or []):
        if not isinstance(rec, dict):
            continue
        offered = rec.get("offeredItem")
        if not isinstance(offered, dict) or not offered.get("item"):
            continue
        index.setdefault(offered["item"], []).append(rec)
    return index


def _trade_entries(item, item_id, barter_index):
    """由上游字段推出**逐笔交易**（购买与兑换分开成条，各自带商人 / 等级 / 任务 / 价格）。

    字段（全部来自上游真实记录，取不到就留空，**不用价格或商人名猜**）：
      `k` 来源类型（flea / buy / barter）；`t` 商人稳定 id；`l` 商人等级；
      `u` 任务解锁 id；`c` 货币（buy）；`p` 货币价（buy，priceRUB）；
      `r` 兑换所需 `[[itemId, count], …]`（barter）；`o` 兑换产出数量（barter）；
      `x` 1 = 该来源确认存在但**明细未确认**（如上游 types 说能兑换、barters 里却没配方）。

    **购买（buy）与兑换（barter）是不同交易类型，永远是两条，不混成一条。**
    """
    out = []
    types = {t for t in (item.get("types") or []) if isinstance(t, str)}
    if "noFlea" not in types:
        out.append({"k": "flea"})
    bft = item.get("buyFromTrader")
    if isinstance(bft, list):
        for offer in bft:
            if not isinstance(offer, dict):
                continue
            trader_id = offer.get("trader")
            if not trader_id:
                continue
            if offer.get("price") is None and offer.get("priceRUB") is None:
                continue
            out.append(_compact({
                "k": "buy", "t": trader_id, "l": offer.get("minTraderLevel"),
                "c": offer.get("currency"), "p": offer.get("priceRUB") or offer.get("price"),
                "u": offer.get("taskUnlock"),
            }))
    recipes = barter_index.get(item_id) or []
    if recipes:
        for rec in recipes:
            reqs = []
            for need in (rec.get("requiredItems") or []):
                if isinstance(need, dict) and need.get("item"):
                    reqs.append([need["item"], need.get("count")])
            out.append(_compact({
                "k": "barter", "t": rec.get("trader"), "l": rec.get("minTraderLevel"),
                "u": rec.get("taskUnlock"), "r": reqs,
                "o": (rec.get("offeredItem") or {}).get("count"),
            }))
    elif "barter" in types:
        out.append({"k": "barter", "x": 1})   # 确认可兑换，但配方明细未确认
    return out


def _sell_deals(item) -> list:
    """上游 `sellToTrader` → 紧凑卖出报价 `[[商人id, 卢布价], …]`（按价格降序、每个商人取最高）。

    只接受 `priceRUB`（上游已按货币换算成卢布），**不做汇率折算**；
    没有该字段的物品返回空数组（界面显示「暂不可用」，绝不当成 0 元）。
    """
    raw = item.get("sellToTrader")
    if not isinstance(raw, list):
        return []
    best: dict = {}
    for offer in raw:
        if not isinstance(offer, dict):
            continue
        trader = offer.get("trader")
        price = offer.get("priceRUB")
        if not trader or not isinstance(price, (int, float)) or price <= 0:
            continue
        if price > best.get(trader, 0):
            best[trader] = int(price)
    return [[tid, best[tid]] for tid in sorted(best, key=lambda t: (-best[t], t))]


def _contains_items(item) -> list:
    """Preset 物品的 `containsItems` → `[[配件物品id, 数量], …]`。

    内置枪械参考预设（497 套）的配件清单只在这个字段里；落库后构建期即可还原预设，
    用户方案仍然只写 `%APPDATA%`，不会回写这份随包数据。
    """
    raw = item.get("containsItems")
    if not isinstance(raw, list):
        return []
    out = []
    for part in raw:
        if not isinstance(part, dict) or not part.get("item"):
            continue
        out.append([part["item"], part.get("count") or 1])
    return out


def build_items(raw_data, zh, traders_table=None, barters_data=None, tasks_table=None):
    """把上游物品表压成紧凑的 `data/items.json`（构建期纯函数，离线可测）。

    `traders_table` / `barters_data` / `tasks_table` 都是可选的：只给物品表也能构建
    （此时 `trade` 只有 `flea` 或「可兑换但配方未确认」，顶层 `traders` / `tasks` 为空表），
    这样既有单测不用改就能继续跑。
    只保留界面要用的字段，并对 0 / 空值做省略，把 17 MB 压到几 MB。
    字段含义：`n` 中文名 / `sn` 短名 / `pt` 类型（去掉 `ItemProperties` 前缀）/ `ic` 有图标 /
    `gw,gh` 占地格 / `w` 重量 / `p` 价格（b 基础 / l 上次低价 / a 均价 / lo 今日低 / hi 今日高）/
    `slot` 旧版配装槽位（由 propertiesType 推得，**不可用于根槽位判定**，见 `ts`）/
    `ts` 上游 types（根槽位归属的权威依据：helmet / armor / rig / backpack / glasses /
    headphones / armorPlate …）/ `cat` 一级类别（由 `ts` + 分类 id 判定，见 `CATEGORY_RULES`）/
    `pen` 减益（t 转身 / s 移动 / e 人体工学）/ `cl` 护甲等级 / `dur` 耐久 /
    `mat` 装甲材质 / `at` 装甲类型（Light / Heavy）/ `bt` 钝击穿透 / `z` 防护 zone（去前缀）/
    `cap` 容器容量 / `hp` 耳机参数（d 距离 / a 环境音量 / dv 干音量 / r 失真 / g 压缩增益 /
    gt 压缩阈值）/ `gl` 容器物品级装载限制（`a` 仅允许 / `e` 排除，均为物品 id 列表）/
    `cats,hb` 分类 id / `conflict` 冲突物品 id / `mod` 配件属性（e 人体工学 / r 后坐 / a 精度）/
    `slots` 附件槽树（枪、配件，以及护甲 / 头盔 / 胸挂 / 背包等父装备）/
    `aps` 护甲槽（可装插板槽 `{zone, plates[], z[]}` 与固定内衬 `{zone, fx:1, ...真实防护数据}）/
    `trade` 逐笔获取来源（`k` flea/buy/barter、`t` 商人 id、`l` 等级、`u` 任务解锁、
    `c` 货币、`p` 价格、`r` 兑换所需物品、`o` 兑换产出数量、`x:1` 明细未确认）。

    顶层另附 `materials`（上游 armorMaterials 毁损系数）、`categoryIds`（分类 id 表）、
    `traders`（商人 id → 名称 / 头像）、`tasks`（任务 id → 任务名）、
    `audit`（七个一级类别件数 / 重复归类 / 待审核清单 / 字段覆盖率）。
    """
    items = (raw_data or {}).get("items") or {}
    category_ids = _category_ids(raw_data)
    barter_index = _barter_index(barters_data)
    used_tasks: set = set()
    out: dict = {}
    counts = {key: 0 for key in ROOT_CATEGORY_KEYS}
    counts["plate"] = 0
    duplicates = []
    pending_ids = []
    pending_by_type: dict = {}
    for item_id, item in items.items():
        if not isinstance(item, dict):
            continue
        props = item.get("properties")
        props = props if isinstance(props, dict) else {}
        ptype = props.get("propertiesType") or ""
        cat, matches = _classify_item(item, category_ids)
        trades = _trade_entries(item, item_id, barter_index)
        for entry in trades:
            if entry.get("u"):
                used_tasks.add(entry["u"])
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
            if len(matches) > 1:
                duplicates.append({"id": item_id, "keys": matches, "resolved": cat})
        elif ptype in GEAR_PROPERTY_TYPES:
            pending_ids.append(item_id)
            pending_by_type[ptype] = pending_by_type.get(ptype, 0) + 1
        record = _compact({
            "n": _zh_name(zh, item_id, item),
            "sn": _zh_short_name(zh, item_id, item),
            "pt": ptype.replace("ItemProperties", "") or None,
            "ic": 1 if item.get("iconLink") else None,
            "gw": item.get("width"), "gh": item.get("height"),
            "w": item.get("weight"),
            "p": _compact({"b": item.get("basePrice"), "l": item.get("lastLowPrice"),
                           "a": item.get("avg24hPrice"), "lo": item.get("low24hPrice"),
                           "hi": item.get("high24hPrice")}),
            "slot": GEAR_SLOT_TYPES.get(ptype),
            "ts": [t for t in (item.get("types") or []) if isinstance(t, str) and t],
            # 获取方式（第六项）：构建期判定、随包分发，运行期不联网；多种来源可共存
            "src": _access_sources(item.get("types"), item.get("buyFromTrader")),
            # 逐笔交易（第五轮）：购买与兑换分开成条，带商人 / 等级 / 任务 / 价格 / 配方
            "trade": trades,
            "cat": cat,
            "pen": _compact({"t": props.get("turnPenalty"), "s": props.get("speedPenalty"),
                             "e": props.get("ergoPenalty")}),
            "cl": props.get("class"),
            "dur": props.get("durability") or item.get("maxDurability"),
            "mat": props.get("material"),
            "at": props.get("armorType"),
            "bt": props.get("bluntThroughput"),
            "cap": props.get("capacity"),
            "hp": _headphone_props(props),
            "gl": _grid_limits(props) or None,
            "z": _zones(props.get("zones")),
            "cats": list(item.get("categories") or []),
            "hb": list(item.get("handbookCategories") or []),
            "conflict": list(item.get("conflictingItems") or []),
            "mod": _compact({"e": props.get("ergonomics"), "r": props.get("recoilModifier"),
                             "a": props.get("accuracyModifier")}),
            "slots": _item_slots(props, zh, item_id),
            "aps": _item_armor_slots(props),
            # 卖出价（第六轮）：上游 sellToTrader 的卢布价，按商人去重后降序
            "sl": _sell_deals(item),
            # 内置参考预设的配件清单（只对 Preset 物品有值；用户预设另存 %APPDATA%）
            "ci": _contains_items(item),
            # R286 市场大盘：涨跌 / 在售挂单数 / 最近扫描（上游现成，非成交量）
            "mk": _market_fields(item),
        })
        out[item_id] = record

    coverage = {
        "total": len(out),
        "ts": sum(1 for r in out.values() if r.get("ts")),
        "slots": sum(1 for r in out.values() if r.get("slots")),
        "aps": sum(1 for r in out.values() if r.get("aps")),
        "cat": sum(1 for r in out.values() if r.get("cat")),
        "mat": sum(1 for r in out.values() if r.get("mat")),
        "z": sum(1 for r in out.values() if r.get("z")),
        "at": sum(1 for r in out.values() if r.get("at")),
        "bt": sum(1 for r in out.values() if r.get("bt") is not None),
        "cap": sum(1 for r in out.values() if r.get("cap")),
        "hp": sum(1 for r in out.values() if r.get("hp")),
        "gl": sum(1 for r in out.values() if r.get("gl")),
        "liners": sum(1 for r in out.values()
                      for a in (r.get("aps") or []) if a.get("fx")),
        "plateSlots": sum(1 for r in out.values()
                          for a in (r.get("aps") or []) if a.get("plates")),
        # 卖出价 / 内置预设配件清单的覆盖率（未覆盖 = 界面显示「暂不可用」而不是 0）
        "sell": sum(1 for r in out.values() if r.get("sl")),
        "containsItems": sum(1 for r in out.values() if r.get("ci")),
        # R286 市场大盘字段覆盖率（缺失显示「—」，不补 0、不插值）
        "marketOffer": sum(1 for r in out.values() if "o" in (r.get("mk") or {})),
        "marketChange": sum(1 for r in out.values() if "c" in (r.get("mk") or {})),
        "marketVelocity": sum(1 for r in out.values() if "v" in (r.get("mk") or {})),
        "marketScan": sum(1 for r in out.values() if "s" in (r.get("mk") or {})),
    }
    # 获取方式（第六项）覆盖率：每种来源各多少件、以及「不可获得 / 数据未确认」各多少件
    src_counts = {k: 0 for k in ACCESS_KEYS + ("none", "unknown")}
    for r in out.values():
        for token in (r.get("src") or []):
            if token in src_counts:
                src_counts[token] += 1
    coverage.update({
        "srcAny": sum(1 for r in out.values()
                      if any(t in ACCESS_KEYS for t in (r.get("src") or []))),
        "srcFlea": src_counts["flea"],
        "srcTrader": src_counts["trader"],
        "srcBarter": src_counts["barter"],
        "srcNone": src_counts["none"],
        "srcUnknown": src_counts["unknown"],
    })
    # 减益（`pen`）覆盖率：三个方向各有多少件非零 —— 供「减益字段覆盖率」报告核对
    coverage.update({
        "penT": sum(1 for r in out.values() if (r.get("pen") or {}).get("t")),
        "penS": sum(1 for r in out.values() if (r.get("pen") or {}).get("s")),
        "penE": sum(1 for r in out.values() if (r.get("pen") or {}).get("e")),
        "penAny": sum(1 for r in out.values()
                      if any((r.get("pen") or {}).get(k) for k in ("t", "s", "e"))),
    })
    # 逐笔交易（第五轮）覆盖率：各来源类型多少件、多少件带商人等级、多少件带兑换配方
    trade_counts = {k: 0 for k in TRADE_KINDS}
    for r in out.values():
        kinds = {e.get("k") for e in (r.get("trade") or [])}
        for k in TRADE_KINDS:
            if k in kinds:
                trade_counts[k] += 1
    coverage.update({
        "trAny": sum(1 for r in out.values() if r.get("trade")),
        "trFlea": trade_counts["flea"],
        "trBuy": trade_counts["buy"],
        "trBarter": trade_counts["barter"],
        "trBuyWithLevel": sum(1 for r in out.values()
                              for e in (r.get("trade") or [])
                              if e.get("k") == "buy" and e.get("l")),
        "trBuyWithTask": sum(1 for r in out.values()
                             for e in (r.get("trade") or [])
                             if e.get("k") == "buy" and e.get("u")),
        "trBarterWithRecipe": sum(1 for r in out.values()
                                  for e in (r.get("trade") or [])
                                  if e.get("k") == "barter" and e.get("r")),
        "trBarterWithTask": sum(1 for r in out.values()
                                for e in (r.get("trade") or [])
                                if e.get("k") == "barter" and e.get("u")),
        "trBarterUnconfirmed": sum(1 for r in out.values()
                                   for e in (r.get("trade") or [])
                                   if e.get("k") == "barter" and e.get("x")),
    })
    audit = {
        "labels": CATEGORY_LABELS,
        "rules": CATEGORY_RULES,
        "rootKeys": list(ROOT_CATEGORY_KEYS),
        "counts": counts,
        "duplicates": duplicates,
        "pending": {"count": len(pending_ids), "byType": pending_by_type, "ids": pending_ids},
        "coverage": coverage,
        "materials": _armor_materials(raw_data),
        "categoryIds": category_ids,
        "sources": {
            "labels": ACCESS_LABELS,
            "rules": {
                "flea": "上游 types 不含 noFlea（允许上跳蚤）",
                "trader": "buyFromTrader 有用货币（RUB / USD / EUR）直接购买的报价",
                "barter": "上游 types 含 barter（需消耗其它物品交换）",
                "none": "来源数据完整，但 flea / trader / barter 三种都没有",
                "unknown": "来源数据缺失 / 无法判断（不误判为不可获得）",
            },
            "modes": "上游 regular 为单一数据集，无 PVP / PVE 来源拆分",
            "multi": "多种方式可共存，全部展示，不强行只留一个",
            "trade": "逐笔交易来自 buyFromTrader（购买）与 barters 数据集（兑换）："
                     "`k` 区分 buy / barter，购买与兑换永远分列，不混成一条",
            "traderLevel": "商人等级取上游 minTraderLevel（1–4），界面按罗马数字 I–IV 显示",
            "taskUnlock": "任务解锁取上游 taskUnlock 的任务 id，名称来自 tasks 数据集；"
                          "取不到名称时显示「未确认」，不按商人或价格猜",
            "barterRecipe": "兑换配方取 barters[].requiredItems（物品 id + 数量）；"
                            "上游 types 说可兑换但 barters 里无配方时标「配方未确认」",
            "traderIcons": TRADER_ICON_LICENSE + "，构建期下载到 assets/icons-traders/，"
                          "逐个记录来源 URL 与 SHA-256（见该目录 manifest.json）",
        },
    }
    traders_out = {}
    for tid, rec in (traders_table or {}).items():
        nn = (rec or {}).get("nn")
        traders_out[tid] = _compact({
            "n": (rec or {}).get("n"),
            "nn": nn,
            "img": ("assets/icons-traders/%s.svg" % nn) if nn else None,
            "lic": TRADER_ICON_LICENSE if nn else None,
        })
    tasks_out = {tid: tasks_table[tid] for tid in sorted(used_tasks)
                 if isinstance(tasks_table, dict) and tasks_table.get(tid)}
    audit["trade"] = {
        "kinds": list(TRADE_KINDS),
        "traders": len(traders_out),
        "tasksResolved": len(tasks_out),
        "tasksReferenced": len(used_tasks),
        "tasksMissing": sorted(tid for tid in used_tasks if tid not in tasks_out),
    }
    return {"schema": ITEMS_SCHEMA, "count": len(out), "items": out,
            "traders": traders_out, "tasks": tasks_out, "audit": audit}


def build_gunslots(raw_data, zh):
    """提取 172 把枪的槽位树与预设（`data/gunslots.json`，供配枪视图使用）。"""
    items = (raw_data or {}).get("items") or {}
    guns: dict = {}
    presets: dict = {}
    for item_id, item in items.items():
        props = item.get("properties") if isinstance(item, dict) else None
        if not isinstance(props, dict):
            continue
        ptype = props.get("propertiesType")
        if ptype == "ItemPropertiesWeapon":
            guns[item_id] = {
                "n": _zh_name(zh, item_id, item),
                "slots": _item_slots(props, zh, item_id),
                "presets": [],
                "default": props.get("defaultPreset"),
                "ergo": props.get("ergonomics"),
                "rv": props.get("recoilVertical"), "rh": props.get("recoilHorizontal"),
                "moa": props.get("centerOfImpact"),
            }
        elif "preset" in (item.get("types") or []) and props.get("baseItem"):
            presets[item_id] = _compact({
                "base": props.get("baseItem"),
                "n": _zh_name(zh, item_id, item),
                "e": props.get("ergonomics"),
                "rv": props.get("recoilVertical"), "rh": props.get("recoilHorizontal"),
                "moa": props.get("moa"),
            })
    for preset_id, preset in presets.items():
        gun = guns.get(preset.get("base"))
        if gun is not None:
            gun["presets"].append(_compact(dict(preset, id=preset_id)))
    # R19.19：AK 照门等价迁移（AKMP RS 并入唯一照门槽 allow），见 tools/slotfix.py
    if slotfix is not None and hasattr(slotfix, "apply_gun_slot_allow_adds"):
        slotfix.apply_gun_slot_allow_adds(guns, getattr(slotfix, "R1919_GUN_SLOT_ALLOW_ADDS", {}))
    # 没有槽位树的枪不留空壳，减少体积
    guns = {gid: gun for gid, gun in guns.items() if gun["slots"]}
    # presetCount 是上游总数（497）；presetCountInFile 才是随本文件分发、能挂到枪上的
    # 那部分（基础枪械没有槽位树的上游预设不落库），meta 里两个数都要写清楚。
    return {"schema": ITEMS_SCHEMA, "count": len(guns),
            "presetCount": len(presets),
            "presetCountInFile": sum(len(gun["presets"]) for gun in guns.values()),
            "guns": guns}


def items_ready():
    """物品资料库是否已就绪（items.json + gunslots.json + 图标目录）。"""
    index = DATA_DIR / "items.json"
    if not index.exists() or not (DATA_DIR / "gunslots.json").exists():
        return False
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 索引损坏就当作未就绪
        return False
    if payload.get("schema") != ITEMS_SCHEMA or not payload.get("items"):
        return False
    return (ROOT / "assets" / "icons-items").is_dir()


def _load_items_zh(args):
    """物品中文名表（`items_zh`）：优先本地缓存，缺失时联网；返回 (dict, raw_bytes)。"""
    cache = CACHE_DIR / ("items_zh.json" if args.mode == "regular" else "items_zh-%s.json" % args.mode)
    if cache.exists() and not args.force:
        raw = cache.read_bytes()
    else:
        raw = fetch(ITEMS_ZH_URL.format(mode=args.mode), timeout=TIMEOUT_LARGE)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    data = json.loads(raw.decode("utf-8", "replace"))
    return data.get("data", data), raw


def _download_icons(ids):
    """并发下载物品图标到 `assets/icons-items/{id}.webp`（增量：已存在的跳过）。"""
    ids = sorted({i for i in ids if i})
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    todo = [i for i in ids if not (ICONS_DIR / ("%s.webp" % i)).exists()]
    print("      图标：需下载 %d / %d 件（其余已存在）" % (len(todo), len(ids)))
    if not todo:
        return len(ids), _dir_bytes(ICONS_DIR)

    def one(item_id):
        try:
            raw = fetch(ITEM_ICON_URL.format(id=item_id), browser_ua=True, timeout=TIMEOUT_SMALL)
            write_atomic(ICONS_DIR / ("%s.webp" % item_id), raw)
            return 1
        except Exception:  # noqa: BLE001 - 单个图标失败不影响整体，运行期该图标回退占位
            return 0

    done = 0
    with ThreadPoolExecutor(max_workers=ICON_WORKERS) as pool:
        for step, ok in enumerate(pool.map(one, todo), 1):
            done += ok
            if step % 500 == 0:
                print("        已处理 %d / %d …" % (step, len(todo)))
    have = sum(1 for i in ids if (ICONS_DIR / ("%s.webp" % i)).exists())
    print("      图标：本次下载 %d 件，本地共 %d 件（%.1f MB）" % (done, have, _dir_bytes(ICONS_DIR) / 1024 / 1024))
    return have, _dir_bytes(ICONS_DIR)


def _dir_bytes(path):
    total = 0
    for entry in path.glob("*"):
        try:
            total += entry.stat().st_size
        except OSError:
            continue
    return total


def _trader_svg(name, initials):
    """项目内自绘的商人「头像式」图标：圆形底 + 半身剪影（头 + 肩）+ 小缩写。

    完全用几何图形自绘，不含任何第三方素材与真实人物肖像（许可结论见 licenseReview）。
    32×32，纯 SVG，无外链字体与滤镜；运行期用 <img> 引用本地文件即可。
    剪影按商人名做稳定取色，16 位商人彼此可辨。
    """
    label = name.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    # 稳定取色：同一商人每次构建都得到同一颜色（不随机、可复核）
    palette = ["#7c8a5c", "#8a6f5c", "#5c7d8a", "#8a5c6f",
               "#6f5c8a", "#8a825c", "#5c8a6f", "#78838a"]
    accent = palette[sum(ord(c) for c in name) % len(palette)]
    size = 7.0 if len(initials) <= 2 else 6.0
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" '
        'role="img" aria-label="%s">'
        '<circle cx="16" cy="16" r="14.5" fill="#1b1f18" stroke="%s" stroke-width="1.5"/>'
        # 头部
        '<circle cx="16" cy="12.2" r="4.5" fill="%s"/>'
        # 肩部（左右各 8.8 宽，收在圆内不溢出）
        '<path d="M7.2 27.4a8.8 8.8 0 0 1 17.6 0z" fill="%s"/>'
        # 缩写压在肩部，帮助快速辨认
        '<text x="16" y="25.4" text-anchor="middle" '
        'font-family="Segoe UI, Arial, sans-serif" font-size="%s" font-weight="700" '
        'fill="#12160f">%s</text></svg>'
    ) % (label, accent, accent, accent, size, initials)


def _build_crafts_stations(crafts_data, hideout_data, force=False):
    """构建「藏身处制作」表与设施表，并顺手下载设施图标（assets/icons-hideout/*.png）。

    返回 (crafts, stations)：
      crafts   = {产物 itemId: [[设施 normalizedName, 设施等级, 任务 id 或 None], …]}
      stations = {normalizedName: {"n": 英文显示名, "icon": 本地图标路径或 ""}}
    单张图标失败不影响制作表（前端对缺失图标有 onerror 兜底）。
    """
    def title(nn):
        return " ".join(w.upper() if w == "btr" else (w[:1].upper() + w[1:])
                        for w in str(nn).split("-") if w)

    hdata = (hideout_data or {}).get("data", hideout_data) or {}
    cdata = (crafts_data or {}).get("data", crafts_data) or []
    by_id = {rec.get("id"): (rec.get("normalizedName") or "") for rec in hdata.values()}

    out_dir = ROOT / "assets" / "icons-hideout"
    out_dir.mkdir(parents=True, exist_ok=True)
    stations = {}
    for rec in hdata.values():
        nn = rec.get("normalizedName") or ""
        if not nn:
            continue
        dest = out_dir / ("%s.png" % nn)
        if force or not dest.exists():
            try:
                raw = fetch(HIDEOUT_ICON_URL.format(name=nn), browser_ua=True,
                            timeout=TIMEOUT_SMALL)
                write_atomic(dest, raw)
            except Exception:  # noqa: BLE001 - 单张图标失败不阻塞制作表
                pass
        stations[nn] = {"n": title(nn),
                        "icon": ("assets/icons-hideout/%s.png" % nn) if dest.exists() else ""}

    crafts = {}
    for c in cdata:
        pid = (c.get("productItem") or {}).get("item") or ""
        st = by_id.get(c.get("station") or "") or ""
        if not pid or not st:
            continue
        # R300：附带配方材料（排除 tool 类可复用工具）与产物数量，供配装估值按材料跳蚤价估算。
        reqs = []
        for need in (c.get("requiredItems") or []):
            if not isinstance(need, dict) or not need.get("item"):
                continue
            attrs = need.get("attributes") or {}
            if attrs.get("tool"):
                continue
            reqs.append([need["item"], need.get("count") or 1])
        out_count = (c.get("productItem") or {}).get("count") or 1
        crafts.setdefault(pid, []).append(
            [st, int(c.get("level") or 0), c.get("taskUnlock") or None, reqs, out_count]
        )
    return crafts, stations


def _download_trader_portraits(wanted, force=False):
    """下载 16 位商人的**游戏头像**到 `assets/icons-traders/portraits/{traderId}.webp`。

    R23.2：用户决定改用游戏素材（学术研究、非商用）。下载策略与物品图标一致：
    增量（已存在即跳过）、并发、单张失败不影响其余（运行期回退自绘 SVG）。
    返回 (files, have, missing)。
    """
    TRADER_PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    files = {}
    missing = []
    todo = []
    for tid, nn, disp in wanted:
        dest = TRADER_PORTRAITS_DIR / ("%s.webp" % tid)
        if dest.exists() and not force:
            files[tid] = {"file": "assets/icons-traders/portraits/%s.webp" % tid,
                          "name": disp, "bytes": dest.stat().st_size,
                          "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                          "url": TRADER_PORTRAIT_URL.format(id=tid)}
            continue
        todo.append((tid, nn, disp))

    if todo:
        def one(item):
            tid, _nn, disp = item
            try:
                raw = fetch(TRADER_PORTRAIT_URL.format(id=tid), browser_ua=True, timeout=TIMEOUT_SMALL)
                write_atomic(TRADER_PORTRAITS_DIR / ("%s.webp" % tid), raw)
                return (tid, disp, raw, None)
            except Exception as err:  # noqa: BLE001 - 单张失败不影响其余，运行期回退 SVG
                return (tid, disp, None, str(err))

        with ThreadPoolExecutor(max_workers=8) as pool:
            for tid, disp, raw, err in pool.map(one, todo):
                if raw is None:
                    missing.append(tid)
                    continue
                files[tid] = {"file": "assets/icons-traders/portraits/%s.webp" % tid,
                              "name": disp, "bytes": len(raw),
                              "sha256": hashlib.sha256(raw).hexdigest(),
                              "url": TRADER_PORTRAIT_URL.format(id=tid)}
    have = len(files)
    print("      商人头像：游戏素材 %d / %d 位%s"
          % (have, len(wanted), ("，缺失 %d" % len(missing)) if missing else ""))
    return files, have, missing


def _write_trader_icons(trader_ids, traders):
    """生成 16 位商人的**项目内自绘**中性图标，并刷新可复核的 manifest（不联网）。

    为什么不再下载上游头像：许可复核（详见 manifest.licenseReview 与文件头注释）确认
    the-hideout/tarkov-dev 的 MIT 只覆盖源代码，图片素材没有任何明确的再分发许可，
    tarkov.dev 自身也声明游戏素材版权归 Battlestate Games。因此这些游戏角色美术
    **不能**当作已获许可资源随包分发，改为自绘缩写图标；商人名称、等级、交易类型、
    兑换配方与任务解锁等业务信息完全保留。

    文件名用规范化英文名（如 prapor.svg），与前端 `assets/icons-traders/{nn}.svg`
    一一对应；旧的下载件记录整体迁到 manifest.removed 留痕，便于审计。
    """
    wanted = []
    for tid in sorted({i for i in trader_ids if i}):
        rec = (traders or {}).get(tid) or {}
        nn = rec.get("nn")
        if nn:
            wanted.append((tid, nn, rec.get("n") or nn))

    TRADER_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    mpath = TRADER_ICONS_DIR / TRADER_ICON_MANIFEST
    old = {}
    if mpath.exists():
        try:
            old = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - manifest 坏了就重建，不影响生成图标
            old = {}
    removed = [r for r in (old.get("removed") or []) if isinstance(r, dict)]
    seen_removed = {r.get("file") for r in removed}
    # 首次迁移：把上一版 manifest 里的下载件逐条记入 removed（文件已从仓库删除）
    legacy = old.get("files") if isinstance(old.get("files"), dict) else {}
    for nn, rec in legacy.items():
        if rec.get("file") in seen_removed:
            continue
        removed.append({
            "file": rec.get("file"),
            "traderId": rec.get("traderId"),
            "name": rec.get("name"),
            "url": rec.get("url"),
            "sha256": rec.get("sha256"),
            "bytes": rec.get("bytes"),
            "reason": "上游游戏角色美术无可再分发许可（MIT 仅覆盖源代码），"
                      "已替换为项目内自绘中性图标",
            "removedAt": _now_iso(),
        })

    local_files = {}
    for name, desc in TRADER_LOCAL_ICONS.items():
        path = TRADER_ICONS_DIR / ("%s.svg" % name)
        if not path.exists():
            continue
        raw = path.read_bytes()
        local_files[name] = {
            "file": "assets/icons-traders/%s.svg" % name,
            "url": "",
            "source": "项目内自绘（SVG 源码随仓库提交）",
            "license": TRADER_ICON_LICENSE,
            "description": desc,
            "downloadedAt": "",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }

    for tid, nn, disp in wanted:
        initials = TRADER_INITIALS.get(nn)
        if not initials:
            words = nn.replace("-", " ").split()
            initials = "".join(w[0] for w in words)[:2].upper() or "?"
        raw = _trader_svg(disp, initials).encode("utf-8")
        path = TRADER_ICONS_DIR / ("%s.svg" % nn)
        if not path.exists() or path.read_bytes() != raw:
            write_atomic(path, raw)
        local_files[nn] = {
            "traderId": tid,
            "name": disp,
            "file": "assets/icons-traders/%s.svg" % nn,
            "url": "",
            "source": "项目内自绘（SVG 源码随仓库提交）",
            "license": TRADER_ICON_LICENSE,
            "description": "商人 %s 的中性缩写图标（%s，项目内自绘）" % (disp, initials),
            "downloadedAt": "",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }

    missing = [nn for _tid, nn, _disp in wanted if not (TRADER_ICONS_DIR / ("%s.svg" % nn)).exists()]
    have = len(wanted) - len(missing)
    portrait_files, portrait_have, portrait_missing = _download_trader_portraits(wanted)
    payload = {
        "note": "商人头像默认使用**游戏素材**（assets/icons-traders/portraits/{traderId}.webp，"
                "构建期从 assets.tarkov.dev 下载，用途为学术研究/非商用，与本项目物品图标同源）；"
                "同目录下的 {normalizedName}.svg 为项目内自绘兜底图标，仅在头像文件缺失/加载失败时使用。"
                "历史许可复核保留在 licenseReview，本轮改用的决定见 decision。",
        "license": TRADER_PORTRAIT_LICENSE,
        "decision": {
            "decidedAt": "2026-10-30",
            "by": "项目所有者（用户）",
            "content": "商人头像直接使用游戏素材；本项目用于学术研究、不商用。"
                       "所有互动地图类工具均使用游戏素材，且本项目既有的物品图标与地图瓦片同源。"
                       "因此不再以「无再分发许可」为由弃用上游头像。",
            "runtimeIcon": "assets/icons-traders/portraits/{traderId}.webp",
            "fallbackIcon": "assets/icons-traders/{normalizedName}.svg",
        },
        "portraits": {
            "dir": "assets/icons-traders/portraits",
            "count": portrait_have,
            "total": len(wanted),
            "missing": portrait_missing,
            "license": TRADER_PORTRAIT_LICENSE,
            "files": portrait_files,
        },
        "licenseReview": {
            "reviewedAt": _now_iso(),
            "scope": "16 位商人的头像（原 assets/icons-traders/*.webp）",
            "checked": [
                {"source": "https://github.com/the-hideout/tarkov-dev/blob/main/LICENSE",
                 "finding": "MIT，覆盖的是项目源代码，未提图片素材"},
                {"source": "https://github.com/the-hideout/tarkov-dev/blob/main/README.md",
                 "finding": "未声明图片素材许可或再分发条件"},
                {"source": "https://github.com/the-hideout/.github/blob/main/profile/docs/infrastructure.md",
                 "finding": "仅说明图片经 S3 + Cloudflare 分发，未给许可"},
                {"source": "https://tarkov.dev/ 页面页脚",
                 "finding": "Game content and materials are trademarks and copyrights of "
                            "Battlestate Games and its licensors. All rights reserved."},
                {"source": "https://assets.tarkov.dev/",
                 "finding": "纯 CDN，无独立许可页，不构成再分发授权"},
            ],
            "conclusion": "未找到允许再分发这些游戏角色美术的许可；不将「公开可下载 / 署名 / 非商业」"
                          "视为 MIT 或 CC BY-NC-SA。",
            "status": "superseded",
            "supersededBy": "decision（2026-10-30 项目所有者决定：学术研究/非商用，改用游戏素材）",
            "runtimeIcon": "assets/icons-traders/{normalizedName}.svg",
        },
        "count": have,
        "total": len(wanted),
        "missing": missing,
        "files": {},
        "localFiles": local_files,
        "removed": removed,
    }
    write_atomic(mpath, json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"))
    print("      商人图标：头像 %d / %d 位（游戏素材），兜底 SVG %d 位"
          % (portrait_have, len(wanted), have))
    return have, _dir_bytes(TRADER_ICONS_DIR), payload


def _build_items_stage(args):
    """构建物品资料库 + 图标；返回 (meta 顶层块, 追加的 source 条目)。"""
    print("[物品] 读取上游物品资料库（17 MB）…")
    items_data, items_bytes = load_json_cached(
        ITEMS_URL.format(mode=args.mode), "items-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_LARGE,
    )
    items_zh, items_zh_bytes = _load_items_zh(args)
    raw_data = items_data.get("data", items_data)

    # 商人 / 兑换配方 / 任务名（第五轮）：获取方式要显示「哪个商人 · 几级 · 购买还是兑换」，
    # 这些信息不在 items 数据集里，单独三个上游数据集，同样构建期拉一次、随包分发。
    print("[物品] 读取上游商人 / 兑换配方 / 任务名 …")
    traders_data, traders_bytes = load_json_cached(
        TRADERS_URL.format(mode=args.mode), "traders-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_SMALL,
    )
    traders_zh, traders_zh_bytes = load_json_cached(
        TRADERS_ZH_URL.format(mode=args.mode), "traders_zh.json",
        force=args.force, timeout=TIMEOUT_SMALL,
    )
    barters_data, barters_bytes = load_json_cached(
        BARTERS_URL.format(mode=args.mode), "barters-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_SMALL,
    )
    tasks_data, tasks_bytes = load_json_cached(
        TASKS_URL.format(mode=args.mode), "tasks-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_SMALL,
    )
    traders_table = _trader_table(traders_data.get("data", traders_data),
                                  traders_zh.get("data", traders_zh))
    tasks_raw = tasks_data.get("data", tasks_data)
    tasks_table = _task_table(tasks_raw.get("tasks", tasks_raw) if isinstance(tasks_raw, dict) else {})
    barters_list = barters_data.get("data", barters_data)
    if isinstance(barters_list, dict):
        barters_list = barters_list.get("barters", [])
    print("      商人 %d 位 · 兑换配方 %d 条 · 任务 %d 个"
          % (len(traders_table), len(barters_list), len(tasks_table)))

    items_payload = build_items(raw_data, items_zh, traders_table, barters_list, tasks_table)
    # R79：眼镜等类目上游不给 zones，用游戏文件（game-truth）的 armorColliders 补齐，
    # 否则配装界面的「防护区域」列看不到「眼部」。只补空值，不覆盖上游已有数据。
    _filled = apply_truth_zone_fallback(items_payload)
    if _filled:
        print("      防护区域补齐 %d 件（来源 data/game-truth/armor_items.json）" % _filled)
    # R20.3：先算出最终落盘字节，再写盘。meta 里的 bytes 与 sha256 都取自这同一份字节，
    # 保证「大小」与「哈希」描述的是同一个文件内容（不改变序列化/变换/排序行为）。
    items_bytes = json.dumps(items_payload, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
    write_atomic(DATA_DIR / "items.json", items_bytes)
    gunslots_payload = build_gunslots(raw_data, items_zh)
    gunslots_bytes = json.dumps(gunslots_payload, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8")
    write_atomic(DATA_DIR / "gunslots.json", gunslots_bytes)

    # R22.1：跳弹角(rc.z)/听力防护(df) → data/item-extra.json（独立文件，不覆盖 items.json 的
    # SHA-256 契约，对齐 flea-prices.json 先例）。上游 items 数据的 ricochetX/Y/Z + deafening。
    extra_items = {}
    _src_items = raw_data.get("items") or {}
    _src_map = _src_items if isinstance(_src_items, dict) else \
        {i["id"]: i for i in _src_items if isinstance(i, dict) and "id" in i}
    for _iid, _v in _src_map.items():
        _p = (_v.get("properties") or {})
        _df = _p.get("deafening")
        _rc = _compact_keep_zero({"x": _p.get("ricochetX"), "y": _p.get("ricochetY"),
                                  "z": _p.get("ricochetZ")}) or None
        _rec = {}
        if _df is not None:
            _rec["df"] = _df
        if _rc:
            _rec["rc"] = _rc
        if _rec:
            extra_items[_iid] = _rec
    # R27.0：藏身处制作 + 设施表：获取方式要显示「齿轮 + 设施图标 + 设施等级（罗马数字）」，
    # 任务解锁再挂一个问号。同样落在 item-extra.json（不覆盖 items.json 契约）。
    print("[物品] 读取上游藏身处制作 / 设施 …")
    crafts_data, _crafts_bytes = load_json_cached(
        CRAFTS_URL.format(mode=args.mode), "crafts-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_LARGE,
    )
    hideout_data, _hideout_bytes = load_json_cached(
        HIDEOUT_URL.format(mode=args.mode), "hideout-%s.json" % args.mode,
        force=args.force, timeout=TIMEOUT_LARGE,
    )
    crafts_map, stations = _build_crafts_stations(crafts_data, hideout_data, force=args.force)
    print("      藏身处：%d 个设施、%d 种可制作产物" % (len(stations), len(crafts_map)))

    extra_payload = {"schema": 1, "count": len(extra_items),
                     "note": "跳弹角(rc.z)/听力防护(df)/藏身处制作(crafts)/设施(stations)"
                             "——独立于 items.json（不覆盖其 SHA-256 契约）",
                     "items": extra_items,
                     "crafts": crafts_map,
                     "stations": stations}
    write_atomic(DATA_DIR / "item-extra.json",
                 json.dumps(extra_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    icon_ids = [i for i, rec in items_payload["items"].items() if rec.get("ic")]
    icon_count, icon_bytes = _download_icons(icon_ids)
    trader_count, trader_bytes, trader_manifest = _write_trader_icons(
        [tid for tid, rec in items_payload["traders"].items() if rec.get("nn")], traders_table)

    # 内置枪械参考预设：把 Preset 的配件清单按真实槽位关系回溯成 {槽位路径: 配件 id}，
    # 独立落 `data/gun-presets.json`；用户的枪械预设另存 %APPDATA%，绝不写回这里。
    gun_presets = gpresets.build(gunslots_payload, items_payload["items"])
    gun_presets_file = DATA_DIR / "gun-presets.json"
    gun_presets_bytes = json.dumps(gun_presets, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8")
    write_atomic(gun_presets_file, gun_presets_bytes)
    # 同内容再落一份 JS 赋值：配枪视图直接读全局变量，避免为 373 套预设再发一次 fetch
    write_atomic(DATA_DIR / "gun-presets.js",
                 ("window.__GUN_PRESETS__ = "
                  + json.dumps(gun_presets, ensure_ascii=False, separators=(",", ":"))
                  + ";\n").encode("utf-8"))
    gp_stats = gpresets.stats(gun_presets)
    meta_blocks = {
        "items": {"file": "data/items.json", "schema": ITEMS_SCHEMA, "count": items_payload["count"],
                  "bytes": len(items_bytes),
                  # R20.3：本地文件哈希（对应上面那份最终落盘字节）。
                  # 注意与 sources[].sha256 区分：那是**上游响应**哈希，这里是**本地文件**哈希。
                  "sha256": hashlib.sha256(items_bytes).hexdigest(),
                  # 字段覆盖率：新提取的护甲字段到底覆盖多少件，写进数据来源记录里可审计
                  "coverage": items_payload["audit"]["coverage"],
                  "categories": items_payload["audit"]["counts"],
                  "pending": items_payload["audit"]["pending"]["count"],
                  "trade": items_payload["audit"]["trade"]},
        "gunslots": {"file": "data/gunslots.json", "schema": ITEMS_SCHEMA,
                     "count": gunslots_payload["count"],
                     # presets = 文件内实际挂载的内置预设；presetsUpstream = 上游总数
                     "presets": gunslots_payload.get("presetCountInFile", gunslots_payload["presetCount"]),
                     "presetsUpstream": gunslots_payload["presetCount"],
                     "bytes": len(gunslots_bytes),
                     "sha256": hashlib.sha256(gunslots_bytes).hexdigest()},
        "gunPresets": {"file": "data/gun-presets.json", "schema": gpresets.SCHEMA,
                       "count": gp_stats["count"], "unsolved": gp_stats["unsolved"],
                       "bytes": len(gun_presets_bytes),
                       "sha256": hashlib.sha256(gun_presets_bytes).hexdigest()},
        "icons": {"dir": "assets/icons-items", "count": icon_count, "bytes": icon_bytes},
        "traderIcons": {"dir": "assets/icons-traders", "count": trader_count,
                        "total": trader_manifest["total"], "missing": trader_manifest["missing"],
                        "bytes": trader_bytes, "license": TRADER_ICON_LICENSE,
                        "manifest": "assets/icons-traders/" + TRADER_ICON_MANIFEST},
    }
    extra_sources = [
        source_entry("tarkov.dev 物品资料库（json.tarkov.dev）", ITEMS_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", items_bytes),
        source_entry("tarkov.dev 中文物品名（json.tarkov.dev）", ITEMS_ZH_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", items_zh_bytes),
        source_entry("tarkov.dev 商人表（json.tarkov.dev）", TRADERS_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", traders_bytes),
        source_entry("tarkov.dev 商人中文名（json.tarkov.dev）", TRADERS_ZH_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", traders_zh_bytes),
        source_entry("tarkov.dev 兑换配方（json.tarkov.dev）", BARTERS_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", barters_bytes),
        source_entry("tarkov.dev 任务表（json.tarkov.dev）", TASKS_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", tasks_bytes),
        source_entry("物品图标（assets.tarkov.dev）", "https://assets.tarkov.dev/",
                     "tarkov.dev 社区公开数据（署名 tarkov.dev，非商业）", b""),
        source_entry("商人图标（项目内自绘）", "",
                     TRADER_ICON_LICENSE, b""),
    ]
    print("      物品 %d 件（%.1f MB）· 枪械 %d 把 / 预设 %d 套 · 图标 %d 个 · 商人头像 %d 个"
          % (items_payload["count"], (DATA_DIR / "items.json").stat().st_size / 1024 / 1024,
             gunslots_payload["count"], gunslots_payload["presetCount"], icon_count, trader_count))
    return meta_blocks, extra_sources


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


def _build_roadnet(selected_keys):
    """第 5 步：把矢量底图栅格化成前端寻路用的静态路网（纯离线，不联网）。

    ``import`` 放在函数里是有意的：``roadnet`` 反过来要用本模块的 ``write_atomic``，
    在模块顶层互相 import 会撞上「半初始化模块」。
    """
    print("[5/5] 栅格化底图路网（离线）…")
    import roadnet  # noqa: PLC0415
    roadnet.build_all(selected_keys)


def _now_iso():
    """UTC 时间戳（秒级，Z 结尾）：写入 meta 的 generatedAt。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _merge_sources(existing, extra):
    """按标题合并来源条目：同标题就地覆盖，新标题追加到尾部（不产生重复署名行）。

    `source_entry` 的键是 `name`（不是 `title`）：早先按 `title` 合并时永远取不到键，
    每跑一次 items 阶段就会把同一批来源再追加一遍，meta.sources 里堆出 6 条重复的
    「物品图标」。这里按 `name + url` 合并，同时清掉历史遗留的同名重复条目。
    """
    def key_of(entry):
        return (entry.get("name") or entry.get("title") or "", entry.get("url") or "")

    out = []
    index = {}
    for entry in (existing or []):
        k = key_of(entry)
        if k not in index:
            index[k] = len(out)
            out.append(entry)
        else:
            out[index[k]] = entry          # 同键只保留最后一条，消除历史重复
    for entry in extra:
        k = key_of(entry)
        pos = index.get(k)
        if pos is None:
            index[k] = len(out)
            out.append(entry)
        else:
            out[pos] = entry
    return out


def _items_only(args):
    """地图数据已就绪时只补物品资料库：读回现有 meta，合并 items 顶层块后重写。

    地图产出（maps.json / 底图 / 路网）一概不动，避免为了补一份物品表把地图全量重拉。
    """
    meta_path = DATA_DIR / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    blocks, extra_sources = _build_items_stage(args)
    meta["sources"] = _merge_sources(meta.get("sources"), extra_sources)
    meta.update(blocks)
    meta["generatedAt"] = _now_iso()
    write_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
    print("完成：物品资料库已补齐（%s），地图产出保持不动" % args.mode)
    return 0


def run(args):
    requested = [k.strip() for k in (args.maps or "").split(",") if k.strip()]
    # meta.json 也要求在，这样「只补物品」这条捷径才有可合并的基础
    maps_done = data_ready(requested) and (DATA_DIR / "meta.json").exists()
    items_done = items_ready()

    if not args.force and maps_done and items_done:
        print("[跳过] data/ 与资源已就绪。要重新拉取请加 --force")
        _build_roadnet(requested)
        return 0

    if not args.force and maps_done:
        return _items_only(args)

    print("[1/5] 读取上游配置与翻译 …")
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

    selected = select_maps(with_event_maps(config), requested)
    markers_map = markers.get("data", markers)["maps"]
    markers_by_name = {m.get("normalizedName"): m for m in markers_map.values()}
    print("      配置文件 %s，标注 %s 张图，选中 %s 张" % (len(config), len(markers_map), len(selected)))

    print("[2/5] 准备底图（SVG 下载 / 瓦片拼接）…")
    viewboxes = {}
    svg_tops = {}
    svg_names = {}
    svg_bytes = 0
    tile_bytes_total = 0
    tile_map_count = 0
    for key, entry in selected.items():
        if key in TILE_MAPS:
            apply_tile_layer_ids(entry, key)          # 上游这些层没有 svgLayer，得先补上
            apply_tile_projection(entry, key)         # 上游 transform/bounds 不可信的图换成人工投影
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
            source = EVENT_SVG_SOURCES.get(key)
            if source:
                # 活动图上游没有底图；--force 时也只从原图复制，不要去 404 的 URL
                raw = (ASSETS_DIR / source).read_bytes()
            else:
                raw = fetch(SVG_URL_TEMPLATE.format(name=svg_name[:-4]), browser_ua=True, timeout=TIMEOUT_LARGE)
            text = raw.decode("utf-8", "replace")
            write_atomic(target, raw)
        viewboxes[key] = parse_svg_viewbox(text)
        svg_tops[key] = parse_svg_top_layers(text)
        svg_names[key] = svg_name
        svg_bytes += target.stat().st_size if target.exists() else 0
        print("      %-18s %-38s 图层=%s" % (key, svg_name, svg_tops[key]))

    print("[3/5] 规范化标注数据 …")
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

    print("[物品] 构建物品资料库（items / gunslots / 图标）…")
    meta_blocks, item_sources = _build_items_stage(args)

    print("[4/5] 写入 data/maps.json 与 data/meta.json …")
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
        # 实验室 / 迷宫 / 破冰船上游只有瓦片：构建期按上游 transform + bounds 把瓦片拼成合成 SVG 底图
        source_entry("瓦片底图（tarkov.dev 地图瓦片，实验室 / 迷宫 / 破冰船）", "https://assets.tarkov.dev/maps/",
                     "tarkov.dev 社区公开数据（署名 tarkov.dev，非商业）", b""),
    ]
    sources = _merge_sources(sources, item_sources)
    generated_at = _now_iso()
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
    meta.update(meta_blocks)          # items / gunslots / icons 三个顶层块（与 counts 平级）
    write_atomic(DATA_DIR / "maps.json", json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"))
    write_atomic(DATA_DIR / "meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))

    _build_roadnet(requested)

    print(
        "完成：%d 张图 / 底图 %.1f MB / 索引 %.0f KB · 物品 %d 件（%s）"
        % (len(maps), svg_bytes / 1024 / 1024, (DATA_DIR / "maps.json").stat().st_size / 1024,
           meta_blocks["items"]["count"], args.mode)
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
