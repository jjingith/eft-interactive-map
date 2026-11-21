# -*- coding: utf-8 -*-
"""构建期工具：从 tarkov.dev 官方静态数据提取枪械射速与射击模式。

来源：https://json.tarkov.dev/{mode}/items （与 tools/fetch_data.py 使用的同一数据源）
字段：properties.fireRate（发/分钟）、properties.fireModes（如 single / fullauto）

产物：data/gun-rates.json（运行期只读本地文件，页面不发起任何外部请求）

用法：
  python tools/fetch_fire_rates.py                 # 联网下载后生成
  python tools/fetch_fire_rates.py --src D:/x.json # 使用已下载的 items JSON
  python tools/fetch_fire_rates.py --proxy 127.0.0.1:7896
"""
import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUNSLOTS = os.path.join(ROOT, "data", "gunslots.json")
OUT = os.path.join(ROOT, "data", "gun-rates.json")
ITEMS_URL = "https://json.tarkov.dev/regular/items"

MODE_ZH = {"single": "单发", "fullauto": "全自动", "burst": "三连发", "doublet": "双连发",
           "doubleaction": "双动", "shotgun": "霰弹"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch(url, proxy):
    opener = urllib.request.build_opener()
    if proxy:
        handler = urllib.request.ProxyHandler({"http": "http://" + proxy, "https": "http://" + proxy})
        opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, headers={"User-Agent": "eft-map-r15/1.0"})
    with opener.open(req, timeout=240) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="本地已下载的 items JSON 路径")
    ap.add_argument("--proxy", default="", help="HTTP/HTTPS 代理，如 127.0.0.1:7896")
    args = ap.parse_args()

    source_kind = "remote" if not args.src else "local-cache"
    if args.src:
        payload = load_json(args.src)
    else:
        payload = fetch(ITEMS_URL, args.proxy)

    items = (payload.get("data") or {}).get("items") or {}
    gunslots = load_json(GUNSLOTS).get("guns") or {}

    guns, missing = {}, []
    for gid, rec in gunslots.items():
        it = items.get(gid)
        props = (it or {}).get("properties") or {}
        rpm = props.get("fireRate")
        modes = props.get("fireModes") or []
        if not isinstance(rpm, (int, float)) or rpm <= 0:
            missing.append({"id": gid, "n": rec.get("n") or gid,
                            "reason": "上游 items 数据无 fireRate 字段"})
            continue
        guns[gid] = {
            "n": rec.get("n") or (it.get("name") or gid),
            "rpm": int(round(rpm)),
            "modes": [{"k": m, "n": MODE_ZH.get(m, m)} for m in modes],
        }

    out = {
        "schema": 1,
        "generatedAt": time.strftime("%Y-%m-%d"),
        "sourceKind": source_kind,
        "source": {
            "url": ITEMS_URL,
            "fields": ["properties.fireRate", "properties.fireModes"],
            "note": "tarkov.dev 官方静态数据（与 tools/fetch_data.py 同源）；fireRate 为该枪械名义射速（发/分钟），"
                    "射击时间间隔 Δt = 60000 / rpm 毫秒。仅构建期使用，运行期只读本地文件。",
        },
        "count": len(guns),
        "missingCount": len(missing),
        "missing": missing,
        "guns": guns,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    print("written %s | guns=%d missing=%d" % (OUT, len(guns), len(missing)))
    if missing:
        print("missing(前 5):", json.dumps(missing[:5], ensure_ascii=False))


if __name__ == "__main__":
    main()
