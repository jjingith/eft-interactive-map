"""从 tarkov.dev 下载高清物品原图，抠图/裁边后生成新的地图图标。

- 数据源：`https://assets.tarkov.dev/<物品 id>-512.webp`（512×512，透明底；缺失时回退 64px 图标）
- 处理：透明底直接裁掉空白边；万一是不透明图，按四角底色抠图；再等比缩放到 128×128 画布内
- 产物：`assets/icons-hd/<图标 key>.png` + `data/hd-item-icons.json`（图标 key / 物品 id / 名称 / 来源）

只替换「有对应游戏物品」的图标：高级资源点 9 类、赛季文件 8 类，
以及物资容器里确实是物品的 5 类（旅行包 / 武器箱 / 手榴弹箱 / 医疗物品箱 / 物资箱）。
夹克衫、Scav 尸体、抽屉、彩蛋点、收银机、保险箱、机箱属于场景容器，游戏中没有对应物品图，
保留原图标。

用法：python tools/fetch_hd_item_icons.py
"""

import io
import json
import os
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "assets", "icons-hd")
MANIFEST = os.path.join(DATA, "hd-item-icons.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eft-interactive-map/1.0",
      "Referer": "https://tarkov.dev/"}
URL_512 = "https://assets.tarkov.dev/%s-512.webp"
URL_64 = "https://assets.tarkov.dev/%s-icon.webp"
SIZE = 128
PAD = 2

# 图标 key → (游戏物品 id, 中文名)
VALUABLES = {
    "valuable_btc": ("59faff1d86f7746c51718c9c", "实体比特币"),
    "valuable_bottle": ("5d1b376e86f774252519444e", "“凶狠跑刀崽”私酒"),
    "valuable_gpu": ("57347ca924597744596b4e71", "显示卡"),
    "valuable_keycard": ("5c1d0d6d86f7744bb2683e1f", "实验室钥匙卡·黄"),
    "valuable_key": ("5938504186f7740991483f30", "宿舍203房间钥匙"),
    "valuable_med": ("5c0530ee86f774697952d952", "LEDX 皮肤透照仪"),
    "valuable_defib": ("5c052e6986f7746b207bc3c9", "便携式除颤器"),
    "valuable_intel": ("5c12613b86f7743bbe2c3f76", "情报文件夹"),
    "valuable_folder": ("6389c8c5dbfd5e4b95197e6b", "TerraGroup“蓝色文件夹”材料"),
}

CONTAINERS = {
    "duffle": ("56e33634d2720bd8058b456b", "旅行包"),
    "weapon": ("59fb023c86f7746d0d4b423c", "武器箱"),
    "grenade": ("5e2af55f86f7746d4159f07c", "手榴弹箱"),
    "med": ("5aafbcd986f7745e590fff23", "医疗物品箱"),
    "supply": ("6658892e6e007c6f33662002", "已解锁的物资箱（普通）"),
}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def strip_background(img):
    """透明底直接裁边；不透明图按四角底色做近似抠图。"""
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    lo, hi = alpha.getextrema()
    if lo >= 250:   # 完全不透明：按四角底色抠
        corners = [img.getpixel((0, 0)), img.getpixel((img.width - 1, 0)),
                   img.getpixel((0, img.height - 1)), img.getpixel((img.width - 1, img.height - 1))]
        bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                d = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
                if d <= 12:
                    px[x, y] = (0, 0, 0, 0)
                elif d <= 40:
                    px[x, y] = (r, g, b, int(a * (d - 12) / 28))
    box = img.getbbox()
    if not box:
        raise RuntimeError("抠图后没有可见内容")
    return img.crop(box)


def make_icon(raw, key):
    img = strip_background(Image.open(io.BytesIO(raw)))
    if img.width == 0 or img.height == 0:
        raise RuntimeError("图片为空")
    k = min((SIZE - PAD * 2) / float(img.width), (SIZE - PAD * 2) / float(img.height))
    w = max(1, int(round(img.width * k)))
    h = max(1, int(round(img.height * k)))
    img = img.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((SIZE - w) // 2, (SIZE - h) // 2))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, key + ".png")
    canvas.save(path, "PNG", optimize=True)
    return os.path.relpath(path, ROOT).replace("\\", "/"), canvas.size


def main():
    docs = json.load(open(os.path.join(DATA, "season-documents.json"), encoding="utf-8"))
    mapping = dict(VALUABLES)
    for t in docs.get("types") or []:
        mapping["doc_" + t["key"]] = (t["itemId"], t["nameZh"])
    mapping.update(CONTAINERS)

    manifest = {"schema": 1,
                "source": "https://assets.tarkov.dev/<itemId>-512.webp（tarkov.dev 开源数据）",
                "note": "游戏素材版权归 Battlestate Games，仅作学术研究/非商用；构建期下载，运行期离线",
                "size": SIZE,
                "icons": {}}
    ok = failed = 0
    for key, (item_id, name) in mapping.items():
        url = URL_512 % item_id
        try:
            raw = fetch(url)
            rel, size = make_icon(raw, key)
            ok += 1
            manifest["icons"][key] = {"itemId": item_id, "name": name, "file": rel,
                                      "source": url, "size": list(size)}
            print("%-22s %-5s %s" % (key, "512px", rel))
            continue
        except Exception as exc:  # noqa: BLE001
            last = exc
        try:
            raw = fetch(URL_64 % item_id)
            rel, size = make_icon(raw, key)
            ok += 1
            manifest["icons"][key] = {"itemId": item_id, "name": name, "file": rel,
                                      "source": URL_64 % item_id, "size": list(size), "fallback64": True}
            print("%-22s %-5s %s（512 不可用）" % (key, "64px", rel))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("%-22s 下载失败：%s / %s" % (key, last, exc))

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("\n完成：%d 个图标（失败 %d）→ %s" % (ok, failed, MANIFEST))


if __name__ == "__main__":
    main()
