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
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coord import compute_world_to_svg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "maps"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "build-cache"

MARKERS_URL = "https://json.tarkov.dev/{mode}/maps"
MARKERS_ZH_URL = "https://json.tarkov.dev/{mode}/maps_zh"
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


def select_maps(config, requested):
    """从上游配置里挑出有 SVG 底图的图（M1 只收录这类）。"""
    available = {}
    for group in config:
        for entry in group.get("maps") or []:
            if entry.get("svgPath"):
                available[entry["key"]] = entry
    if not requested:
        return available
    unknown = [key for key in requested if key not in available]
    if unknown:
        raise ValueError(
            "这些图没有 SVG 底图（M1 无法收录）：%s\n      可选：%s"
            % (", ".join(unknown), ", ".join(sorted(available)))
        )
    return {key: available[key] for key in requested}


def build_map(entry, markers_by_name, translations, svg_viewbox):
    """把单张图的配置 + 标注 + 翻译拼成前端要用的精简结构。"""
    key = entry["key"]
    marker_map = markers_by_name.get(key)
    if marker_map is None:
        raise ValueError("上游标注数据里找不到图 %s" % key)

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
        x, z = flatten_positions(item.get("position") or {})
        if x is None or z is None:
            continue
        raw_name = item.get("name") or ""
        extracts.append(
            {
                "name": localize(translations, raw_name, raw_name),
                "faction": item.get("faction") or "shared",
                "x": round(float(x), 3),
                "z": round(float(z), 3),
            }
        )

    transits = []
    for item in marker_map.get("transits") or []:
        x, z = flatten_positions(item.get("position") or {})
        if x is None or z is None:
            continue
        raw_desc = item.get("description") or ""
        transits.append(
            {
                "name": localize(translations, raw_desc, raw_desc),
                "x": round(float(x), 3),
                "z": round(float(z), 3),
            }
        )

    spawns = []
    for item in marker_map.get("spawns") or []:
        x, z = flatten_positions(item.get("position") or {})
        if x is None or z is None:
            continue
        spawns.append(
            {
                "x": round(float(x), 3),
                "z": round(float(z), 3),
                "sides": sorted(item.get("sides") or []),
                "categories": sorted(item.get("categories") or []),
            }
        )

    labels = []
    for item in entry.get("labels") or []:
        text = (item.get("text") or "").strip()
        x, z = flatten_positions(item.get("position"))
        if not text or x is None or z is None:
            continue
        labels.append({"text": text, "x": round(float(x), 3), "z": round(float(z), 3)})

    return {
        "key": key,
        "id": map_id,
        "name": name,
        "svg": "assets/maps/%s" % svg_basename(entry),
        "viewBox": svg_viewbox,
        # 底图铺满的世界坐标矩形（供前端推算外边距，也供测试校验角点不变式）
        "svgBounds": [[float(svg_bounds[0][0]), float(svg_bounds[0][1])],
                      [float(svg_bounds[1][0]), float(svg_bounds[1][1])]],
        "svgLayer": entry.get("svgLayer"),
        "worldToSvg": {k: world_to_svg[k] for k in "abcdef"},
        "labels": labels,
        "layers": {"extracts": extracts, "transits": transits, "spawns": spawns},
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
    translations_raw = fetch(MARKERS_ZH_URL.format(mode=args.mode), timeout=TIMEOUT_LARGE)
    translations = json.loads(translations_raw.decode("utf-8", "replace"))
    translations = translations.get("data", translations)

    selected = select_maps(config, requested)
    markers_map = markers.get("data", markers)["maps"]
    markers_by_name = {m.get("normalizedName"): m for m in markers_map.values()}
    print("      配置文件 %s，标注 %s 张图，选中 %s 张" % (len(config), len(markers_map), len(selected)))

    print("[2/4] 下载底图 SVG 并读取 viewBox …")
    viewboxes = {}
    svg_bytes = 0
    for key, entry in selected.items():
        svg_name = svg_basename(entry)
        target = ASSETS_DIR / svg_name
        if target.exists() and not args.force:
            text = target.read_text(encoding="utf-8", errors="replace")
        else:
            raw = fetch(SVG_URL_TEMPLATE.format(name=svg_name[:-4]), browser_ua=True, timeout=TIMEOUT_LARGE)
            text = raw.decode("utf-8", "replace")
            write_atomic(target, raw)
        viewboxes[key] = parse_svg_viewbox(text)
        svg_bytes += target.stat().st_size if target.exists() else 0
        print("      %-18s %-38s viewBox=%s" % (key, svg_name, viewboxes[key]))

    print("[3/4] 规范化标注数据 …")
    maps = []
    for key in selected:
        item = build_map(selected[key], markers_by_name, translations, viewboxes[key])
        maps.append(item)
        print(
            "      %-18s 撤离 %3d / 过境 %2d / 出生 %3d / 标注 %2d"
            % (key, len(item["layers"]["extracts"]), len(item["layers"]["transits"]),
               len(item["layers"]["spawns"]), len(item["labels"]))
        )

    print("[4/4] 写入 data/maps.json 与 data/meta.json …")
    sources = [
        source_entry("tarkov.dev 地图配置（the-hideout/tarkov-dev）", MAP_CONFIG_URL, "MIT", config_raw),
        source_entry("tarkov.dev 标注数据（json.tarkov.dev）", MARKERS_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", markers_raw),
        source_entry("tarkov.dev 中文翻译（json.tarkov.dev）", MARKERS_ZH_URL.format(mode=args.mode),
                     "tarkov.dev 社区公开数据", translations_raw),
        source_entry("底图 SVG（the-hideout/tarkov-dev-svg-maps）", "https://assets.tarkov.dev/maps/svg/",
                     "CC BY-NC-SA 4.0（署名 + 非商业 + 同许可）", b""),
    ]
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "schema": 1,
        "gameMode": args.mode,
        "generatedAt": generated_at,
        "sources": sources,
        "maps": maps,
    }
    meta = {
        "schema": 1,
        "generatedAt": generated_at,
        "gameMode": args.mode,
        "tool": "tools/fetch_data.py",
        "sources": sources,
        "counts": {
            "maps": len(maps),
            "extracts": sum(len(m["layers"]["extracts"]) for m in maps),
            "transits": sum(len(m["layers"]["transits"]) for m in maps),
            "spawns": sum(len(m["layers"]["spawns"]) for m in maps),
            "labels": sum(len(m["labels"]) for m in maps),
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
