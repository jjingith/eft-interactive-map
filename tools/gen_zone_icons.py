#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防护区域图 —— 从现有素材抠图 + 依据数据自动拼（R31.2）。

**不再程序绘图**。每个防护部位都从用户提供的源素材里**单独抠出来**：
- 躯干：以最全的 防护部位-颈部肩部胸部胃部侧面腹股沟.png 为基准帧，
  连通域 + "有肩/无肩"、"胸部侧面" 源图对比定位，抠出 颈/肩/胸/胃/侧/腹股沟 6 块。
- 头部：8 张源图同为同一幅画的不同裁剪（高亮区高均 96px），
  以最全的 防弹部位-头顶后脑面部下颚眼部耳部.png 为基准帧，
  逐图做平移对齐后用「多区域图 − 少区域图」差集抠出 顶/后脑/面/颚/眼/耳 6 块。
- 各部位 piece 保留源图**原始像素与明暗**（只把区域外变透明），观感与源素材一致。
- 组合图：按 data/items.json 的真实 z → 部位词 → piece，在共享画布上叠放后裁剪输出。
  同 zone 组合的装备必得同一张图（PACA = BNTI = DRD = PLATEminus V2 =「胸区+侧面」）。

仅依赖 PIL；运行期不联网。
"""
import json
import os
import shutil
from collections import deque
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "items.json")
ZONES_DIR = os.path.join(ROOT, "assets", "icons", "zones")
PARTS_DIR = os.path.join(ZONES_DIR, "parts")
STAGE = os.path.join(ROOT, "build-cache", "zone-gen")
SRC = r"D:\personal\trae\02-塔科夫\ui图标"
SRC_TORSO = os.path.join(SRC, "防弹衣防弹胸挂防护部位图")
SRC_HEAD = os.path.join(SRC, "头盔防护部位图")

MARGIN = 3  # 组合图裁剪留白

# 部位词（与 app.js ZONE_WORD_ORDER 对齐；下胸并入胸部）
WORD_ORDER = ["头顶", "后脑", "面部", "下颚", "眼部", "耳部",
              "颈部", "肩部", "胸部", "侧面", "腹股沟"]


def zone_word(z):
    if not z:
        return None
    if z.startswith("Plate_"):
        r = z[len("Plate_"):]
        return "侧面" if "side" in r else "胸部"
    table = {
        "ParietalHead": "头顶", "BackHead": "后脑", "HeadCommon": "面部", "Jaw": "下颚",
        "Eyes": "眼部", "Ears": "耳部",
        "NeckFront": "颈部", "NeckBack": "颈部",
        "LeftUpperArm": "肩部", "RightUpperArm": "肩部",
        "RibcageUp": "胸部", "RibcageLow": "胸部",     # 下胸并入胸区（含胃部）
        "LeftSideChestDown": "侧面", "RightSideChestDown": "侧面",
        "Pelvis": "腹股沟", "PelvisBack": "腹股沟",
        "SpineTop": "胸部", "SpineDown": "胸部",       # 上背/下背并入胸区，正反面统一
    }
    return table.get(z)


WORD_TO_PARTS = {
    "胸部": ["chest"], "侧面": ["side"], "腹股沟": ["groin"],
    "颈部": ["neck"], "肩部": ["shoulder"],
    "头顶": ["top"], "后脑": ["back"], "面部": ["face"],
    "下颚": ["jaw"], "眼部": ["eyes"], "耳部": ["ears"],
}

# 共享画布：头部帧在上，躯干帧在下（颈与下颌衔接）
HEAD_W, HEAD_H = 150, 139
TORSO_W, TORSO_H = 77, 78
TORSO_OX, TORSO_OY = (HEAD_W - TORSO_W) // 2, 112   # 头部内容约到 y109，躯干紧随其后
CANVAS_W, CANVAS_H = HEAD_W, TORSO_OY + TORSO_H


def lum(c):
    return (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000


def load_rgb(path):
    return Image.open(path).convert("RGB")


def bright_mask(im, thr=100):
    """亮区掩膜（背景≈23 / 颈影≈40 / 高亮≥140）。返回 (w,h,set[(x,y)])。"""
    w, h = im.size
    px = im.load()
    pts = set()
    for y in range(h):
        for x in range(w):
            if lum(px[x, y]) > thr:
                pts.add((x, y))
    return w, h, pts


def components(pts, min_n=12):
    """4 邻接连通域。"""
    seen = set()
    out = []
    for p in pts:
        if p in seen:
            continue
        q = deque([p])
        seen.add(p)
        comp = []
        while q:
            cx, cy = q.popleft()
            comp.append((cx, cy))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cx + dx, cy + dy)
                if n in pts and n not in seen:
                    seen.add(n)
                    q.append(n)
        if len(comp) >= min_n:
            out.append(comp)
    return out


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def align_subset(sub_pts, full_pts, rng=50):
    """把子集图的高亮点集平移对齐到基准帧：搜索使 |∩|−3·|sub∖full| 最大的整数偏移。"""
    fx0, fy0, fx1, fy1 = bbox(full_pts)
    best, best_off = None, (0, 0)
    # 粗搜（步长 3）
    for dy in range(-rng, rng + 1, 3):
        for dx in range(-rng, rng + 1, 3):
            inter = sum(1 for x, y in sub_pts if (x + dx, y + dy) in full_pts)
            score = inter - 3 * (len(sub_pts) - inter)
            if best is None or score > best:
                best, best_off = score, (dx, dy)
    # 精搜（±3 步长 1）
    bx, by = best_off
    for dy in range(by - 3, by + 4):
        for dx in range(bx - 3, bx + 3 + 1):
            inter = sum(1 for x, y in sub_pts if (x + dx, y + dy) in full_pts)
            score = inter - 3 * (len(sub_pts) - inter)
            if score > best:
                best, best_off = score, (dx, dy)
    dx, dy = best_off
    aligned = {(x + dx, y + dy) for x, y in sub_pts}
    inside = sum(1 for p in aligned if p in full_pts)
    frac = inside / max(1, len(aligned))
    return aligned, (dx, dy), frac


def keep_big(pts, min_n=12):
    out = set()
    for comp in components(pts, min_n=min_n):
        out.update(comp)
    return out


def dilate(pts, r=1):
    """8 邻域膨胀：差集前膨胀被减集合，消除对齐残晕。"""
    out = set()
    for x, y in pts:
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                out.add((x + dx, y + dy))
    return out


# ---------------------------------------------------------------- 躯干：连通域抠图
def cut_torso():
    master = load_rgb(os.path.join(SRC_TORSO, "防护部位-颈部肩部胸部胃部侧面腹股沟.png"))
    w, h, pts = bright_mask(master)
    comps = components(pts, min_n=40)
    info = []
    for c in comps:
        info.append((bbox(c), c))
    info.sort(key=lambda t: (t[0][1], t[0][0]))

    pieces = {}
    px = master.load()

    neck = shoulder_l = shoulder_r = chest = stomach = groin = None
    for bb, c in info:
        x0, y0, x1, y1 = bb
        if y0 < 10 and x0 >= 20:
            neck = c                                   # (27,4)-(48,8)
        elif x1 < 21 and y0 < 45:
            shoulder_l = c                             # (9,10)-(19,38)
        elif x0 > 54 and y0 < 45:
            shoulder_r = c                             # (56,10)-(66,37)
        elif 13 <= y0 <= 17 and (x1 - x0) > 25:
            chest = c                                  # (21,15)-(54,41)
        elif 44 <= y0 <= 48:
            stomach = c                                # (20,46)-(55,64)（含侧条）
        elif y0 >= 64:
            groin = c                                  # (19,67)-(56,74)
    assert neck and chest and stomach and groin and shoulder_l and shoulder_r, \
        "躯干连通域定位失败：%s" % [bb for bb, _ in info]

    # 侧面窄条来自 防护部位-胸部侧面.png（与全图同基准：胸块 bbox 完全一致）
    cs = load_rgb(os.path.join(SRC_TORSO, "防护部位-胸部侧面.png"))
    _, _, cs_pts = bright_mask(cs)
    side = set()
    for comp in components(cs_pts, min_n=30):
        bb = bbox(comp)
        if bb[1] >= 44 and (bb[2] - bb[0]) <= 8:       # 窄竖条
            side.update(comp)
    assert side, "侧面窄条定位失败"

    # 胃部 = 胃块减去左右侧条列（x≤24 / x≥51）
    stomach_only = {(x, y) for (x, y) in stomach if 25 <= x <= 50}

    def cut(m):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ip = img.load()
        for x, y in m:
            r, g, b = px[x, y]
            ip[x, y] = (r, g, b, 255)
        x0, y0, x1, y1 = bbox(m)
        return img.crop((x0, y0, x1 + 1, y1 + 1)), x0, y0   # piece + 帧内偏移

    return {
        "neck": cut(neck),
        "shoulder": cut(set(shoulder_l) | set(shoulder_r)),
        "chest": cut(chest),
        "stomach": cut(stomach_only),
        "side": cut(side),
        "groin": cut(groin),
    }


# ---------------------------------------------------------------- 头部：差集抠图
HEAD_SETS = {
    "back": "防弹部位-后脑.png",
    "top_back": "防弹部位-头顶后脑.png",
    "top_back_ears": "防弹部位-头顶后脑耳部.png",
    "top_back_jaw_ears": "防弹部位-头顶后脑下颚耳部.png",
    "top_back_face_jaw_ears": "防弹部位-头顶后脑面部下颚耳部.png",
    "top_back_face_jaw_eyes": "防弹部位-头顶后脑面部下颚眼部.png",
    "full": "防弹部位-头顶后脑面部下颚眼部耳部.png",
}


def cut_head():
    frames = {}
    full_im = load_rgb(os.path.join(SRC_HEAD, HEAD_SETS["full"]))
    fw, fh, full_pts = bright_mask(full_im)
    assert (fw, fh) == (HEAD_W, HEAD_H), "头部基准帧尺寸变化：%dx%d" % (fw, fh)
    masks = {}
    for key, fn in HEAD_SETS.items():
        im = load_rgb(os.path.join(SRC_HEAD, fn))
        _, _, pts = bright_mask(im)
        if key == "full":
            masks[key] = set(pts)
        else:
            aligned, off, frac = align_subset(pts, full_pts)
            print("  align %-24s off=%s inside=%.1f%%" % (key, off, frac * 100))
            assert frac > 0.9, "对齐失败（子集落框比例过低）：%s %.1f%%" % (key, frac * 100)
            masks[key] = aligned

    def diff(a, b):
        return keep_big(masks[a] - dilate(masks.get(b, set()), 1))

    region = {
        "back": keep_big(masks["back"]),
        "top": diff("top_back", "back"),
        "ears": diff("top_back_ears", "top_back"),
        "jaw": diff("top_back_jaw_ears", "top_back_ears"),
        "face": diff("top_back_face_jaw_ears", "top_back_jaw_ears"),
        "eyes": diff("top_back_face_jaw_eyes", "top_back_face_jaw_ears"),
    }
    px = full_im.load()
    out = {}
    for name, m in region.items():
        assert m, "头部区域为空：%s" % name
        img = Image.new("RGBA", (HEAD_W, HEAD_H), (0, 0, 0, 0))
        ip = img.load()
        for x, y in m:
            r, g, b = px[x, y]
            ip[x, y] = (r, g, b, 255)
        x0, y0, x1, y1 = bbox(m)
        out[name] = (img.crop((x0, y0, x1 + 1, y1 + 1)), x0, y0)  # piece + 帧内偏移
        print("  head piece %-6s n=%5d bbox=%s" % (name, len(m), (x0, y0, x1, y1)))
    return out


# ---------------------------------------------------------------- 组合
# ------------------------------------------------- 用户手绘图优先（画一张顶一张）
# 约定目录 assets/icons/zones/hand/：放 11 张单部位图，文件名含下列任一别名即可（中文优先）。
#   透明底、只画该部位本身即可（画布可以是紧凑的），工具自动等比缩放并对位到人体正确位置。
# 没有 hand/ 或某部位没画 → 该部位继续沿用现有素材抠图，其余照常拼合。
HAND_DIR = os.path.join(ZONES_DIR, "hand")
HAND_ALIAS = {
    "chest":    ["胸部", "胸", "chest"],
    "side":     ["侧面", "侧身", "side"],
    "groin":    ["腹股沟", "裆部", "groin"],
    "neck":     ["颈部", "脖子", "neck"],
    "shoulder": ["肩部", "肩膀", "shoulder"],
    "top":      ["头顶", "颅顶", "top", "parietal"],
    "back":     ["后脑", "backhead", "back_head"],
    "face":     ["面部", "face"],
    "jaw":      ["下颚", "下巴", "jaw"],
    "eyes":     ["眼部", "eyes"],
    "ears":     ["耳部", "ears"],
}


def _norm(s):
    return os.path.splitext(s)[0].strip().lower().replace(" ", "").replace("-", "")


def find_hand(name):
    """在手绘目录里找该部位的图片；找不到返回 None。"""
    if not os.path.isdir(HAND_DIR):
        return None
    want = {_norm(a) for a in HAND_ALIAS.get(name, [])} | {_norm(name)}
    for fn in sorted(os.listdir(HAND_DIR)):
        if not fn.lower().endswith((".png", ".webp")):
            continue
        if _norm(fn) in want:
            return os.path.join(HAND_DIR, fn)
    return None


def fit_part(src_path, box_w, box_h):
    """手绘部位等比缩放，塞进该部位原有占位框并居中；透明底保留。"""
    im = Image.open(src_path).convert("RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    sw, sh = im.size
    scale = min(box_w / float(sw), box_h / float(sh))
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    return im.resize((nw, nh), Image.LANCZOS)


def apply_hand_drawn(pieces):
    """手绘优先：hand/ 里有的部位用用户的图，其余继续用现有素材抠的 piece。"""
    used = []
    for name, (im, ox, oy) in list(pieces.items()):
        if name not in HAND_ALIAS:
            continue
        src = find_hand(name)
        if not src:
            continue
        fitted = fit_part(src, im.width, im.height)
        pieces[name] = (fitted,
                        ox + (im.width - fitted.width) // 2,
                        oy + (im.height - fitted.height) // 2)
        used.append("%-9s ← %s" % (name, os.path.basename(src)))
    if used:
        print("== 手绘部位接管（%d/%d）==" % (len(used), len(HAND_ALIAS)))
        for u in used:
            print("   ", u)
    else:
        print("== 无手绘稿（%s 为空）→ 全部沿用现有素材抠图 ==" % HAND_DIR)
    return pieces


def compose(pieces, wanted):
    base = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    head = Image.new("RGBA", (HEAD_W, HEAD_H), (0, 0, 0, 0))
    for name in ("back", "face", "top", "jaw", "eyes", "ears"):
        if name in wanted:
            im, ox, oy = pieces[name]
            head.alpha_composite(im, (ox, oy))            # 用抠图时的帧内偏移还原位置
    base.alpha_composite(head, (0, 0))
    torso = Image.new("RGBA", (TORSO_W, TORSO_H), (0, 0, 0, 0))
    for name in ("neck", "shoulder", "chest", "stomach", "side", "groin"):
        if name in wanted:
            im, ox, oy = pieces[name]
            torso.alpha_composite(im, (ox, oy))
    base.alpha_composite(torso, (TORSO_OX, TORSO_OY))
    bb = base.getbbox()
    return base.crop((max(0, bb[0] - MARGIN), max(0, bb[1] - MARGIN),
                      min(CANVAS_W, bb[2] + MARGIN), min(CANVAS_H, bb[3] + MARGIN)))


def unique_word_keys():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    keys = {}
    for it in data.get("items", {}).values():
        z = it.get("z")
        if not isinstance(z, list) or not z:
            continue
        words = []
        for zz in z:
            w = zone_word(zz)
            if w and w not in words:
                words.append(w)
        if not words:
            continue
        key = "|".join(w for w in WORD_ORDER if w in words)
        keys[key] = keys.get(key, 0) + 1
    return keys


def main():
    os.makedirs(STAGE, exist_ok=True)
    for fn in os.listdir(ZONES_DIR):
        if fn.endswith(".png"):
            os.remove(os.path.join(ZONES_DIR, fn))
    print("== 抠取躯干部位（现有素材）==")
    pieces = cut_torso()
    print("== 抠取头部部位（现有素材差集）==")
    pieces.update(cut_head())
    pieces = apply_hand_drawn(pieces)
    os.makedirs(PARTS_DIR, exist_ok=True)
    os.makedirs(HAND_DIR, exist_ok=True)
    for name, (im, _ox, _oy) in pieces.items():
        im.save(os.path.join(PARTS_DIR, "region-%s.png" % name))

    keys = unique_word_keys()
    jobs, mapping = [], {}
    for key in sorted(keys):
        words = key.split("|")
        wanted = []
        for w in words:
            for p in WORD_TO_PARTS.get(w, []):
                if p not in wanted:
                    wanted.append(p)
        img = compose(pieces, wanted)
        fname = "zone-" + "-".join(wanted) + ".png"
        img.save(os.path.join(ZONES_DIR, fname))
        shutil.copyfile(os.path.join(ZONES_DIR, fname), os.path.join(STAGE, fname))
        mapping[key] = "assets/icons/zones/" + fname
        jobs.append(["防护部位图（现有素材抠图拼合）", fname, fname, words])
        print("  combo %-40s parts=%s" % (key, ",".join(wanted)))

    print("===== ZONE_ICON_BY_WORDS literal =====")
    print("  var ZONE_ICON_BY_WORDS = {")
    for key in sorted(mapping):
        print('    "%s": "%s",' % (key, mapping[key]))
    print("  };")
    man = {"count": len(mapping), "mapping": mapping, "jobs": jobs}
    with open(os.path.join(STAGE, "zone-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print("unique combos:", len(mapping))


if __name__ == "__main__":
    main()
