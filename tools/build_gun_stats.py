# -*- coding: utf-8 -*-
"""R19 构建期：从 json.tarkov.dev 提取枪械与配件的战斗属性，生成 data/gun-stats.json。

为什么需要它
------------
本地 `data/items.json` 只保留了构建期有意裁剪的字段（`mod.e` 人机工效、`mod.r` 后坐力百分比），
**没有**枪械的基础后坐力 / 精度(MOA) / 初速 / 射速，也没有配件的精度与初速修正。
没有这些就无法做「整枪属性实时计算」，只能全部标 missing。

做法
----
构建期下载一次上游 `items` 快照（17 MB，缓存在 build-cache/，已被 .gitignore 排除），
按 `propertiesType` 提取：
  · Weapon     -> ergonomics / recoilVertical / recoilHorizontal / accuracy(MOA) /
                  velocity / fireRate / caliber / defaultPreset
  · WeaponMod  -> 同上（配件对整枪的修正，字段同名同单位）
输出只保留枪械槽位可能用到的物品（有 slots 的枪械 / 有 mod_ 槽位的配件 / 瞄具 / 弹匣），
避免把 17 MB 原样塞进仓库。

运行期只读 `data/gun-stats.json`（约几百 KB），零联网。

用法：
    python tools/build_gun_stats.py [--refresh]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "build-cache", "r19-upstream", "items.json")
OUT = os.path.join(ROOT, "data", "gun-stats.json")
URL = "https://json.tarkov.dev/regular/items"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "http://127.0.0.1:7896"

# 上游 properties 里与本项目配枪页相关的字段（实测自 2026-10 快照）
#   枪械(ItemPropertiesWeapon)：ergonomics / recoilVertical / recoilHorizontal /
#                              centerOfImpact(MOA 角度) / fireRate / sightingRange / caliber
#   配件(ItemPropertiesWeaponMod)：ergonomics(修正) / recoilModifier(百分比) / accuracyModifier
#   velocity 在**顶层**字段上（枪械=基础 m/s，配件=百分比修正）
WANT = {
    "ergonomics": "e",
    "recoilVertical": "rv", "recoilHorizontal": "rh",
    "recoilModifier": "rm", "accuracyModifier": "am",
    "centerOfImpact": "coi", "fireRate": "rpm",
    "caliber": "cal", "defaultPreset": "preset",
    "sightingRange": "sr", "effectiveDistance": "eff",
    "deviationMax": "devMax", "recoilDispersion": "disp",
    "cameraSnap": "cam", "recoilAngle": "ra",
}

# R19.1：枪械浏览需要的三个额外字段（只在枪械上出现）
#   fireModes  -> fm  ["single","fullauto"]（浏览页的 Auto / Single / Burst 筛选）
#   caliber    -> cal "Caliber545x39"（浏览页按口径分组）
#   defaultAmmo -> da 弹药物品 id（装配视图的弹药卡片）
WANT_GUN_EXTRA = {"fireModes": "fm", "caliber": "cal", "defaultAmmo": "da"}


def download(force=False):
    if os.path.exists(CACHE) and not force and os.path.getsize(CACHE) > 1_000_000:
        print("使用缓存：%s (%.1f MB)" % (CACHE, os.path.getsize(CACHE) / 1e6))
        return
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    opener.addheaders = [("User-Agent", UA)]
    print("下载上游 items 快照（走代理 %s）…" % PROXY)
    t0 = time.time()
    with opener.open(URL, timeout=300) as r:
        data = r.read()
    with open(CACHE + ".part", "wb") as f:
        f.write(data)
    os.replace(CACHE + ".part", CACHE)
    print("  完成 %.1f MB / %.1f s" % (len(data) / 1e6, time.time() - t0))


def pick_props(props, extra=None):
    out = {}
    if not props:
        return out
    want = dict(WANT)
    if extra:
        want.update(extra)
    for k, short in want.items():
        v = props.get(k)
        if v is None:
            continue
        if isinstance(v, dict):          # caliber: {slug, ...}
            v = v.get("slug") or v.get("name")
        if isinstance(v, list):          # fireModes: ["single","fullauto"]
            out[short] = v
        elif isinstance(v, (int, float, str)):
            out[short] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    download(a.refresh)
    raw = json.load(open(CACHE, encoding="utf-8"))
    # 上游形状：{data: {items: {id: item}, ...}, translations: [...]}
    # 兼容 list（每项带 id）与直接 dict（id -> item）两种变体，统一成 (id, item) 序列
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        raw = raw["data"]
    if isinstance(raw, dict) and isinstance(raw.get("items"), (list, dict)):
        raw = raw["items"]
    if isinstance(raw, dict):
        pairs = list(raw.items())
    else:
        pairs = [(it.get("id"), it) for it in raw]
    print("上游物品数：", len(pairs))

    guns, mods = {}, {}
    for iid, it in pairs:
        if not iid or not isinstance(it, dict):
            continue
        pt = it.get("propertiesType") or it.get("types") and "" or ""
        props = it.get("properties") or {}
        short = pick_props(props)
        # velocity 在顶层：枪械记为基础初速，配件记为百分比修正
        vel = it.get("velocity")
        if isinstance(vel, (int, float)) and vel:
            short["v0"] = vel
        if not short:
            continue
        row = {"n": it.get("name") or it.get("shortName") or "", **short}
        if props.get("propertiesType") == "ItemPropertiesWeapon" or \
                props.get("recoilVertical") is not None:
            short2 = pick_props(props, WANT_GUN_EXTRA)
            row2 = {"n": it.get("name") or it.get("shortName") or "", **short2}
            guns[iid] = row2
        else:
            mods[iid] = row

    out = {
        "schema": 1,
        "round": "R19",
        "source": URL,
        "sourceKind": "tarkov.dev 公开静态数据集（常规模式）",
        "fetchedAt": time.strftime("%Y-%m-%d"),
        "note": ("枪械与配件的基础战斗属性。运行时零联网。"
                 "字段：e=人机工效 rv=垂直后坐力 rh=水平后坐力 acc=精度(MOA) "
                 "v0=初速(m/s) rpm=射速 cal=口径 preset=默认预设 id"),
        "fieldUnits": {
            "e": "人机工效点数（修正值，可正可负）",
            "fm": "射击模式（single/fullauto/burst）",
            "cal": "口径 slug（Caliber545x39 等）",
            "da": "defaultAmmo 物品 id",
            "rv": "垂直后坐力（枪械为基础值，配件为修正值）",
            "rh": "水平后坐力（同上）",
            "acc": "精度 MOA（枪械为基础值，配件为修正值，越小越准）",
            "v0": "初速 m/s（枪械为基础值，配件为修正值）",
            "rpm": "射速 发/分",
        },
        "counts": {"guns": len(guns), "mods": len(mods)},
        "guns": guns,
        "mods": mods,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("输出 %s：gun %d / mod %d，%.0f KB"
          % (os.path.relpath(OUT, ROOT), len(guns), len(mods), os.path.getsize(OUT) / 1024))
    # 抽样自检
    for iid in ("5bf3e03b0db834001d2c4a9c", "5447a9cd4bdc2dbd208b4567"):
        print("  sample", iid, json.dumps(guns.get(iid), ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
