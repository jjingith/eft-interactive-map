#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取 Escape from Tarkov Wiki 官方互动地图，生成本项目的「官方底图」数据。

数据来源：
  https://escapefromtarkov.fandom.com/wiki/Map:<地图名>
  页面内容模型 interactivemap，正文是一段 JSON（categories + markers + mapBounds）。
底图/图标：
  Fandom static CDN（https://static.wikia.nocookie.net/...），按原尺寸下载。

用法：
  python tools/fetch_wiki_maps.py
  python tools/fetch_wiki_maps.py --proxy http://127.0.0.1:7896
  python tools/fetch_wiki_maps.py --maps customs,woods --force

输出：
  data/wiki-maps.json
  assets/wiki-maps/<key>.<png|jpg|webp>
  assets/wiki-icons/cat_<分类 id>.png
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import urllib.parse
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://escapefromtarkov.fandom.com/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")
DATA = os.path.join(ROOT, "data", "wiki-maps.json")
MAP_DIR = os.path.join(ROOT, "assets", "wiki-maps")
ICON_DIR = os.path.join(ROOT, "assets", "wiki-icons")

MAPS = {
    "customs": "Map:Customs",
    "factory": "Map:Factory",
    "ground-zero": "Map:Ground Zero",
    "icebreaker": "Map:Icebreaker",
    "interchange": "Map:Interchange",
    "lighthouse": "Map:Lighthouse",
    "reserve": "Map:Reserve",
    "shoreline": "Map:Shoreline",
    "streets-of-tarkov": "Map:Streets of Tarkov",
    "terminal": "Map:Terminal",
    "the-lab": "Map:The Lab",
    "the-labyrinth": "Map:The Labyrinth",
    "woods": "Map:Woods",
}
NAME_ZH = {
    "customs": "海关", "factory": "工厂", "ground-zero": "中心区", "icebreaker": "破冰船",
    "interchange": "立交桥", "lighthouse": "灯塔", "reserve": "储备站", "shoreline": "海岸线",
    "streets-of-tarkov": "塔科夫街区", "terminal": "码头", "the-lab": "实验室",
    "the-labyrinth": "迷宫", "woods": "森林",
}
CAT_ZH = {
    "exfil_pmc": "PMC 撤离点", "exfil_scav": "Scav 撤离点", "exfil_transit": "转移点",
    "spawn_pmc": "PMC 出生点", "spawn_scav": "Scav 出生点", "spawn_sniper": "狙击手",
    "spawn_boss": "Boss", "spawn_cultist": "邪教徒", "spawn_rogueraider": "黑卫队",
    "lever": "拉杆 / 按钮", "stationarygun": "固定武器", "locked": "上锁的门",
    "loot_key": "钥匙刷新点", "loot_keycard": "钥匙卡刷新点", "loot_loose": "散落物资",
    "container_ammo": "弹药箱", "container_stash": "彩蛋点", "container_cash": "收银机",
    "container_pc": "电脑", "container_dead": "尸体", "container_drawer": "抽屉",
    "container_grenade": "手雷箱", "container_jacket": "夹克", "container_medical": "医疗物资",
    "container_medcase": "医疗箱", "container_safe": "保险箱", "container_duffle": "运动包",
    "container_suitcase": "手提箱", "container_crate": "物资箱", "container_tool": "工具箱",
    "container_weapon": "武器箱", "container_greencrate": "木箱", "quest": "电力面板",
}


def opener(proxy=""):
    handlers = [urllib.request.HTTPRedirectHandler()]
    if proxy:
        handlers.insert(0, urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    o = urllib.request.build_opener(*handlers)
    # Fandom 的 static CDN 会检查 Referer / Accept；缺了会返回 Varnish 403。
    o.addheaders = [("User-Agent", UA),
                    ("Accept", "image/avif,image/webp,image/png,image/*,*/*;q=0.8"),
                    ("Referer", "https://escapefromtarkov.fandom.com/")]
    return o


def get(op, url, timeout=60):
    with op.open(url, timeout=timeout) as r:
        return r.read()


def api_json(op, params):
    params = dict(params, format="json")
    return json.loads(get(op, API + "?" + urllib.parse.urlencode(params)).decode("utf-8"))


def image_info(op, titles):
    out = {}
    titles = sorted(set(titles))
    for i in range(0, len(titles), 50):
        obj = api_json(op, {"action": "query", "prop": "imageinfo", "iiprop": "url|size",
                            "titles": "|".join(titles[i:i + 50])})
        for pid, pg in obj["query"]["pages"].items():
            ii = (pg.get("imageinfo") or [{}])[0]
            out[pg["title"]] = ii
    return out


def clean_desc(text):
    text = (text or "").replace("<br/>", "\n").replace("<br>", "\n").replace("</br>", "\n")
    while "[[File:" in text:
        i = text.index("[[File:")
        j = text.find("]]", i)
        text = text[:i] + text[(j + 2 if j >= 0 else len(text)):]
    text = text.replace("[[", "").replace("]]", "")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def raw_image_url(url):
    """去掉 /revision/latest，取原图；失败时退回原 URL。"""
    return url.split("/revision/latest")[0] if "/revision/latest" in url else url


def download_image(direct, proxied, url, path, force):
    if os.path.exists(path) and not force:
        return
    for op in (direct, proxied):
        try:
            raw = get(op, url)
            im = Image.open(io.BytesIO(raw))
            fmt = (im.format or "").lower()
            ext = ".jpg" if fmt == "jpeg" else ("." + fmt if fmt else ".png")
            target = os.path.splitext(path)[0] + ext
            if os.path.exists(target) and not force:
                return target
            with open(target, "wb") as f:
                f.write(raw)
            return target
        except Exception as e:
            last = e
    raise last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY", ""))
    ap.add_argument("--maps", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    os.makedirs(MAP_DIR, exist_ok=True)
    os.makedirs(ICON_DIR, exist_ok=True)
    op = opener(a.proxy)
    direct = opener("")  # 图片直连；静态 CDN 走代理常被 403
    keys = [k for k in a.maps.split(",") if k] if a.maps else list(MAPS)
    titles = [MAPS[k] for k in keys]

    obj = api_json(op, {"action": "query", "prop": "revisions", "rvprop": "content",
                        "rvslots": "main", "titles": "|".join(titles)})
    pages = obj["query"]["pages"]
    docs = {}
    for pid, pg in pages.items():
        if "revisions" not in pg:
            print("跳过（页面不存在）：", pg.get("title"))
            continue
        docs[pg["title"]] = json.loads(pg["revisions"][0]["slots"]["main"]["*"])

    icon_titles = [c["icon"] for d in docs.values() for c in d.get("categories", []) if c.get("icon")]
    map_titles = ["File:" + d["mapImage"] for d in docs.values()]
    info = image_info(op, icon_titles + map_titles)

    # 每个分类 id 对应一个图标文件（含未在本图出现的分类）
    cat_icon = {}
    for d in docs.values():
        for c in d.get("categories", []):
            title = c.get("icon")
            if not title or not info.get(title, {}).get("url"):
                continue
            base = os.path.join(ICON_DIR, "cat_%s" % c["id"])
            raw = get(direct, info[title]["url"]) if a.force or not any(
                os.path.exists(base + e) for e in (".png", ".webp", ".jpg")) else None
            if raw:
                fmt = (Image.open(io.BytesIO(raw)).format or "PNG").lower()
                ext = ".jpg" if fmt == "jpeg" else "." + fmt
                path = base + ext
                with open(path, "wb") as f:
                    f.write(raw)
            else:
                for e in (".png", ".webp", ".jpg"):
                    if os.path.exists(base + e):
                        path = base + e
                        break
            cat_icon[c["id"]] = os.path.relpath(path, ROOT).replace("\\", "/")

    maps_out = {}
    for key in keys:
        page = MAPS[key]
        if page not in docs:
            continue
        d = docs[page]
        image_title = "File:" + d["mapImage"]
        ii = info.get(image_title, {})
        img = download_image(direct, op, ii.get("url", ""),
                             os.path.join(MAP_DIR, key + ".png"), a.force)
        if not img:
            print("底图下载失败：", key)
            continue
        cats = []
        counts = {}
        for m in d.get("markers", []):
            counts[m["categoryId"]] = counts.get(m["categoryId"], 0) + 1
        for c in d.get("categories", []):
            cid = c["id"]
            cats.append({
                "id": cid, "name": c.get("name") or cid, "nameZh": CAT_ZH.get(cid, c.get("name") or cid),
                "icon": cat_icon.get(cid, ""), "color": c.get("color") or "#fa005a",
                "count": counts.get(cid, 0),
            })
        markers = []
        for m in d.get("markers", []):
            p = m.get("position") or [0, 0]
            pop = m.get("popup") or {}
            markers.append({
                "categoryId": m.get("categoryId"), "id": m.get("id"),
                "x": round(float(p[0]), 2), "y": round(float(p[1]), 2),
                "title": (pop.get("title") or "").strip(),
                "desc": clean_desc(pop.get("description")),
            })
        maps_out[key] = {
            "page": page, "nameZh": NAME_ZH.get(key, key),
            "image": os.path.relpath(img, ROOT).replace("\\", "/"),
            "width": d["mapBounds"][1][0], "height": d["mapBounds"][1][1],
            "categories": cats, "markers": markers,
        }
        print("%-18s %sx%s  %d 标点  %d 分类  %s" % (key, maps_out[key]["width"], maps_out[key]["height"],
                                                   len(markers), len(cats), os.path.getsize(img)))

    out = {"schema": 1, "gameMode": "regular",
           "source": "Escape from Tarkov Wiki Interactive Maps（https://escapefromtarkov.fandom.com/wiki/Special:AllMaps）；底图/图标版权归原作者与 Battlestate Games，本地非商业使用",
           "maps": maps_out}
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("写出", DATA, round(os.path.getsize(DATA) / 1048576, 2), "MB")


if __name__ == "__main__":
    main()
