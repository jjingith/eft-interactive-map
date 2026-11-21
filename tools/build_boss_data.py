#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R16-D/E：构建 Boss / 护卫 / 精英单位数据（血量、装备池、默认插板）。

数据来源：
  · fandom 各页面的 wikitext（MediaWiki API `action=parse&prop=wikitext`），构建期抓取后缓存在
    build-cache/boss-wiki/*.json；运行期只读 data/bosses.json，零网络。
  · 默认前后插板：tarkov.dev 物品数据里该护甲的**默认预设**（types 含 preset、containsItems 含护甲本体）
    的 containsItems 顺序 → 前板 / 后板 / 左侧 / 右侧。Tagilla 专属 AVS 的默认预设给出
    Cult Termite（6 级）+ Global Armor's Steel（4 级），与用户提供的资料一致，可作顺序验证。
    注意：护甲「能装哪些板」（兼容池）≠ 该 Boss「会带哪些板」（生成装备）。

可信度口径：
  verified  = 本次实际读到的页面/数据字段直接给出
  estimated = 由默认预设顺序、名称映射或单页信息推断
  missing   = 没有依据，明确留空

用法：
  python tools/build_boss_data.py            # 只用本地缓存（离线可复现）
  python tools/build_boss_data.py --fetch    # 先用 API 刷新缓存（需代理 127.0.0.1:7896）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_CACHE = os.path.join(ROOT, "build-cache", "boss-wiki")
REMOTE_ITEMS = os.path.join(ROOT, "build-cache", "items-regular.json")
LOCAL_ITEMS = os.path.join(ROOT, "data", "items.json")
OLD_BOSSES = os.path.join(ROOT, "data", "bosses.json")
OUT = os.path.join(ROOT, "data", "bosses.json")
LOADOUTS = os.path.join(ROOT, "docs", "r16-completeness", "boss-loadouts.json")

PAGES = ["Bosses", "Killa", "Reshala", "Shturman", "Tagilla", "Glukhar", "Sanitar", "Kaban",
         "Kollontay", "Partisan", "Knight", "Big Pipe", "Birdeye", "Zryachiy",
         "Shadow of Tagilla", "Vengeful Killa", "The Wedge", "Santa Claus",
         "Cultists", "Rogues", "Black Division"]

ZH = {
    "killa": "Killa", "reshala": "Reshala", "shturman": "Shturman", "tagilla": "Tagilla",
    "glukhar": "Glukhar", "sanitar": "Sanitar", "kaban": "Kaban", "kollontay": "Kollontay",
    "partisan": "Partisan", "knight": "Knight（Goons）", "bigpipe": "Big Pipe（Goons）",
    "birdeye": "Birdeye（Goons）", "zryachiy": "Zryachiy（邪教徒首领）",
    "shadowoftagilla": "Shadow of Tagilla（迷宫）", "vengefulkilla": "Vengeful Killa（迷宫）",
    "thewedge": "The Wedge（破冰船）", "santaclaus": "Santa Claus（活动）",
    "cultistpriest": "Cultist Priest（邪教徒祭司）", "cultistwarrior": "Cultist Warrior（邪教徒武士）",
    "rogue": "Rogue（Rogues 精英）", "blackdivision": "Black Division（黑色师）",
}

BOSS_META = [
    ("Killa", "killa", "boss"), ("Reshala", "reshala", "boss"), ("Shturman", "shturman", "boss"),
    ("Tagilla", "tagilla", "boss"), ("Glukhar", "glukhar", "boss"), ("Sanitar", "sanitar", "boss"),
    ("Kaban", "kaban", "boss"), ("Kollontay", "kollontay", "boss"), ("Partisan", "partisan", "boss"),
    ("Knight", "knight", "goons"), ("Big Pipe", "bigpipe", "goons"), ("Birdeye", "birdeye", "goons"),
    ("Zryachiy", "zryachiy", "boss"),
    ("Shadow of Tagilla", "shadowoftagilla", "special"), ("Vengeful Killa", "vengefulkilla", "special"),
    ("The Wedge", "thewedge", "special"), ("Santa Claus", "santaclaus", "event"),
]

# 精英单位（非正式 Boss，独立目标类型，不与 Boss 混排）
ELITE_META = [
    ("Cultists", "cultistpriest", "Cultist Priest"),
    ("Cultists", "cultistwarrior", "Cultist warrior"),
    ("Rogues", "rogue", None),
    ("Black Division", "blackdivision", None),
]

FACTION_ZH = {"Scavs": "Scav", "Rogues": "Rogue", "Cultists": "邪教徒", "Black Division": "黑色师",
              "None": "无", "USEC": "USEC", "BEAR": "BEAR"}


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


# ———————————————————— wiki 抓取 ————————————————————

def fetch_wikitext(page, proxy="http://127.0.0.1:7896", timeout=30):
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
    url = ("https://escapefromtarkov.fandom.com/api.php?action=parse&page="
           + urllib.parse.quote(page) + "&prop=wikitext&format=json&formatversion=2")
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with opener.open(req, timeout=timeout) as r:
        return json.load(r)


def load_wiki(fetch=False):
    os.makedirs(WIKI_CACHE, exist_ok=True)
    out = {}
    for page in PAGES:
        fn = os.path.join(WIKI_CACHE, page.replace(" ", "_") + ".json")
        if fetch or not os.path.exists(fn):
            try:
                data = fetch_wikitext(page)
                write_json(fn, data)
                time.sleep(0.4)
            except Exception as exc:                      # noqa: BLE001
                print("  ! fetch failed %-20s %s" % (page, exc), file=sys.stderr)
                continue
        if os.path.exists(fn):
            wt = (read_json(fn).get("parse") or {}).get("wikitext")
            if wt:
                out[page] = wt
    return out


# ———————————————————— wikitext 解析 ————————————————————

def grab_int(seg, key):
    i = seg.find(key + ":")
    if i < 0:
        return None
    k = i + len(key) + 1
    while k < len(seg) and seg[k] in " \t":
        k += 1
    s = k
    while s < len(seg) and (seg[s].isdigit() or seg[s] == ","):
        s += 1
    raw = seg[k:s].replace(",", "")
    if not raw.isdigit() or len(raw) > 6:
        return None
    return int(raw)


def health_block_at(w, pos):
    seg = w[pos:pos + 1500]
    hp = {"head": grab_int(seg, "Head"), "chest": grab_int(seg, "Thorax"),
          "stomach": grab_int(seg, "Stomach")}
    arms, legs = grab_int(seg, "Arms"), grab_int(seg, "Legs")
    if arms is None or legs is None:
        return None, None
    hp["leftArm"] = hp["rightArm"] = arms
    hp["leftLeg"] = hp["rightLeg"] = legs
    if any(v is None for v in hp.values()):
        return None, None
    return hp, grab_int(seg, "Total")


def label_before(w, pos):
    seg = w[max(0, pos - 900):pos]
    last, idx = None, 0
    while True:
        i = seg.find("|-|", idx)
        if i < 0:
            break
        j = seg.find("=", i)
        if j > 0:
            cand = seg[i + 3:j].strip()
            if cand and len(cand) < 40:
                last = cand
        idx = i + 3
    if last:
        return last
    i = seg.rfind("'s Health")
    if i > 0:
        start = seg.rfind("!", 0, i)
        if start >= 0:
            return seg[start + 1:i].strip()
    return None


def parse_health_blocks(w):
    blocks, pos = [], 0
    while True:
        i = w.find("Head:", pos)
        if i < 0:
            break
        hp, total = health_block_at(w, i)
        if hp:
            blocks.append({"label": label_before(w, i), "health": hp,
                           "totalStated": total, "sum": sum(hp.values())})
        pos = i + 5
    return blocks


def split_sections(w, start_marker="==Equipment=="):
    i = w.find(start_marker)
    if i < 0:
        return {}
    body = w[i + len(start_marker):]
    for end in ("==Quests==", "==Location==", "==Behavior==", "==Strategy==", "==Trivia=="):
        j = body.find(end)
        if j > 0:
            body = body[:j]
            break
    parts = body.split("|-|")
    out = {}
    if parts:
        out["_pre"] = parts[0]
    for p in parts[1:]:
        eq = p.find("=")
        if eq < 0:
            continue
        out[p[:eq].strip()] = p[eq + 1:]
    return out


def extract_links(text):
    out, seen, i = [], set(), 0
    while True:
        a = text.find("[[", i)
        if a < 0:
            break
        b = text.find("]]", a)
        if b < 0:
            break
        target = text[a + 2:b].split("|")[0].strip()
        if target and not target.lower().startswith(("file:", "image:", "category:")):
            t = target.split("#")[0].strip()
            if t and not t.lower().startswith(("cs:", "fr:", "ru:", "de:", "es:", "ja:", "zh:")):
                if t not in seen:
                    seen.add(t)
                    out.append(t)
        i = b + 2
    return out


def infobox_field(w, field):
    i = w.find("|" + field)
    if i < 0:
        return None
    j = w.find("=", i)
    k = w.find("\n", j)
    return w[j + 1:k].strip()


def strip_links(text):
    out, i, raw = [], 0, (text or "")
    while True:
        a = raw.find("[[", i)
        if a < 0:
            out.append(raw[i:])
            break
        out.append(raw[i:a])
        b = raw.find("]]", a)
        if b < 0:
            out.append(raw[a:])
            break
        out.append(raw[a + 2:b].split("|")[-1])
        i = b + 2
    return "".join(out).strip()


def hp_text(hp):
    return "Head %d / Thorax %d / Stomach %d / Arms %d each / Legs %d each" % (
        hp["head"], hp["chest"], hp["stomach"], hp["leftArm"], hp["leftLeg"])


# ———————————————————— 物品索引 ————————————————————

def build_wiki_index(remote):
    idx = {}
    for iid, rec in remote.items():
        link = rec.get("wikiLink") or ""
        if "/wiki/" not in link:
            continue
        title = urllib.parse.unquote(link.split("/wiki/", 1)[1]).replace("_", " ")
        idx.setdefault(title.lower(), iid)
    return idx


def preset_plates(remote, local, armor_id):
    """该护甲默认预设里的插板，按 containsItems 顺序返回；只保留真正的插板物品。"""
    for pid, rec in remote.items():
        if "preset" not in (rec.get("types") or []):
            continue
        ids = [c.get("item") for c in (rec.get("containsItems") or [])]
        if armor_id not in ids:
            continue
        rest = [x for x in ids if x != armor_id and (local.get(x) or {}).get("cat") == "plate"]
        if rest:
            return rest, pid
    return [], None


def classify(rec):
    slot, cat, pt = rec.get("slot"), rec.get("cat"), rec.get("pt")
    if cat == "plate":
        return "plates"
    if slot == "helmet":
        return "helmets"
    if slot == "face":
        return "faces"
    if slot in ("armor", "rig"):
        return "armor"
    if pt in ("Weapon", "WeaponMod"):
        return "weapons"
    return "other"


# ———————————————————— 单个目标 ————————————————————

def build_entity(page, key, category, wiki, remote, local, wiki_idx, unclassified, label_hint=None):
    w = wiki.get(page)
    if not w:
        return None, "页面未抓到"
    blocks = parse_health_blocks(w)
    if not blocks:
        return None, "页面没有可解析的 Health 表"

    main_block = None
    if label_hint:
        for b in blocks:
            if (b["label"] or "").lower() == label_hint.lower():
                main_block = b
                break
    if main_block is None:
        norm_page = page.lower().replace(" ", "")
        for b in blocks:
            lb = (b["label"] or "").lower().replace(" ", "")
            if lb and (lb in norm_page or norm_page in lb):
                main_block = b
                break
    if main_block is None:
        main_block = blocks[0]

    followers = []
    for b in blocks:
        if b is main_block or not (b["label"] or "").strip():
            continue
        label = b["label"].strip()
        # 页面偶有「护卫表与本体表数值完全相同」的复用表格：不把它当成护卫血量（避免与本体混用）
        same_as_boss = b["health"] == main_block["health"]
        followers.append({
            "k": "follower:" + key + ":" + label.lower().replace(" ", "-").replace("'", ""),
            "n": label, "zh": label,
            "health": None if same_as_boss else b["health"],
            "total": None if same_as_boss else b["sum"],
            "totalStated": b["totalStated"],
            "healthConfidence": "missing" if same_as_boss else
                               ("verified" if b["totalStated"] in (None, b["sum"]) else "estimated"),
            "healthSource": "%s 页面 Health 表（%s）：%s%s" % (
                page, label, hp_text(b["health"]),
                "；与本体数值完全相同，疑似页面复用表格，未采信" if same_as_boss else ""),
            "equipment": None, "equipmentConfidence": "missing",
            "note": "页面只给出该护卫的血量表，未给出可结构化的装备表",
        })

    sections = split_sections(w)
    gear = {"armor": [], "helmets": [], "faces": [], "plates": [], "weapons": [], "other": []}
    titles = {}
    for name, body in sections.items():
        for title in extract_links(body):
            iid = wiki_idx.get(title.lower())
            if not iid:
                unclassified.append({"entity": key, "section": name, "title": title,
                                     "reason": "wiki 标题在 tarkov.dev 中无对应物品"})
                continue
            titles[iid] = title
            bucket = classify(local.get(iid) or {})
            if iid not in gear[bucket]:
                gear[bucket].append(iid)

    default_armor = None
    for aid in gear["armor"]:
        if "edition" in (titles.get(aid) or "").lower():
            default_armor = aid
            break
    if default_armor is None and gear["armor"]:
        default_armor = gear["armor"][0]

    default_plates = None
    if default_armor:
        plates, preset_id = preset_plates(remote, local, default_armor)
        # 顺序按 前 → 后 → 左 → 右；同时校验「该板确实在这个护甲的对应插板槽里」，
        # 不在槽内的一律留空（宁可 missing，也不把别的护甲的板塞进来）
        sockets = {}
        for a in (local.get(default_armor) or {}).get("aps") or []:
            if not a.get("fx"):
                sockets[a["zone"].lower()] = set(a.get("plates") or [])
        want = ["front_plate", "back_plate", "left_side_plate", "right_side_plate"]
        slots = []
        for i, z in enumerate(want):
            pid = plates[i] if i < len(plates) else None
            slots.append(pid if (pid and pid in sockets.get(z, set())) else None)
        plates = [x for x in slots if x]
        if plates:
            default_plates = {
                "armorId": default_armor, "armorTitle": titles.get(default_armor),
                "front": slots[0], "back": slots[1],
                "left": slots[2], "right": slots[3],
                "presetId": preset_id,
                "source": "tarkov.dev 该护甲默认预设的 containsItems 顺序（前→后→侧）",
                "confidence": "estimated",
            }

    missing = []
    if not gear["armor"]:
        missing.append("页面未列出可识别的护甲/胸挂")
    if not gear["helmets"]:
        missing.append("页面未列出头盔")
    if not default_plates:
        missing.append("默认预设中未找到插板（可能为固定内衬或页面无该护甲）")
    if followers:
        missing.append("护卫装备池未结构化（页面只给血量）")

    # 兼容既有读取方：每个目标都必须有 follower 记录；没有护卫数据的写 missing 占位
    if not followers:
        followers.append({
            "k": "follower:" + key, "n": page + " follower", "zh": page + " 护卫",
            "health": None, "total": None, "healthConfidence": "missing",
            "healthSource": "%s 页面未提供该目标的护卫 Health 表" % page,
            "equipment": None, "equipmentConfidence": "missing",
            "note": "无护卫数据：不提供该护卫目标",
        })
        followers_with_data = []
    else:
        followers_with_data = list(followers)

    hp = main_block["health"]
    faction = strip_links(infobox_field(w, "faction") or "")
    ent = {
        "k": key, "n": page, "zh": ZH.get(key, page),
        "category": category, "targetKind": "elite" if category == "elite" else "boss",
        "faction": faction, "factionZh": FACTION_ZH.get(faction),
        "location": strip_links(infobox_field(w, "location") or ""),
        "health": hp, "total": sum(hp.values()), "totalStated": main_block["totalStated"],
        "healthConfidence": "verified" if main_block["totalStated"] in (None, sum(hp.values())) else "estimated",
        "healthSource": "%s 页面 Health 表：%s；页面标注总量 %s" % (
            page, hp_text(hp), main_block["totalStated"]),
        "equipment": {
            "armor": gear["armor"], "helmets": gear["helmets"], "faces": gear["faces"],
            "plates": gear["plates"], "weapons": gear["weapons"], "titles": titles,
            "platesPolicy": "boss-preset" if default_plates else "none",
            "defaultArmor": default_armor, "defaultPlates": default_plates,
            "confidence": "verified" if (gear["armor"] or gear["helmets"]) else "missing",
            "combinationConfidence": "estimated",
            "missing": missing,
        },
        "follower": followers[0],
        "followers": followers_with_data,
        "missing": missing + ([] if followers_with_data else ["页面未给出护卫 Health 表"]),
        "sourcePage": "https://escapefromtarkov.fandom.com/wiki/" + page.replace(" ", "_"),
    }
    return ent, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="先用 fandom API 刷新缓存")
    args = ap.parse_args()

    wiki = load_wiki(fetch=args.fetch)
    if not wiki:
        raise SystemExit("没有可用的 wiki 缓存")
    remote = read_json(REMOTE_ITEMS)["data"]["items"]
    local = read_json(LOCAL_ITEMS)["items"]
    wiki_idx = build_wiki_index(remote)
    old = read_json(OLD_BOSSES) if os.path.exists(OLD_BOSSES) else {}

    unclassified, unresolved = [], []
    bosses, elites = [], []
    for page, key, category in BOSS_META:
        ent, err = build_entity(page, key, category, wiki, remote, local, wiki_idx, unclassified)
        if ent is None:
            unresolved.append({"page": page, "reason": err})
            continue
        bosses.append(ent)
    for page, key, hint in ELITE_META:
        ent, err = build_entity(page, key, "elite", wiki, remote, local, wiki_idx, unclassified,
                                label_hint=hint)
        if ent is None:
            unresolved.append({"page": page, "key": key, "reason": err})
            continue
        elites.append(ent)

    doc = {
        # 沿用既有 schema=1：本轮只做**向后兼容的最小扩展**（新增 elites / followers / defaultPlates），
        # R15 的读取方与测试按原结构仍可用；数据结构版本另记 revision。
        "schema": 1,
        "revision": "r16",
        "generatedAt": _dt.date.today().isoformat(),
        "source": {
            "pages": ["https://escapefromtarkov.fandom.com/wiki/" + p.replace(" ", "_") for p in PAGES],
            "method": "2026-10-22 经代理（127.0.0.1:7896）调用 fandom MediaWiki API "
                      "action=parse&prop=wikitext，缓存 build-cache/boss-wiki/；随后离线解析血量表与装备表。"
                      "物品名→ID 用 tarkov.dev 的 wikiLink 精确匹配；默认插板取该护甲默认预设的 containsItems 顺序。",
            "gameVersion": "页面本身未标注版本；抓取时间 2026-10-22，晚于本地 1.0.6.5.46221（2026-08-01）数据快照，"
                           "版本漂移未逐项比对",
            "note": "血量=页面 Health 表逐项读数（页面总量与逐项和一致才标 verified）；"
                    "装备=页面 Equipment 表列出的物品（页面存在 ≠ 每局必出，组合为 estimated）；"
                    "默认插板=游戏默认预设（estimated，顺序按前→后→侧推断，Tagilla AVS 已用页面资料交叉验证）。"
                    "「物品存在」「护甲兼容」「Boss 实际会使用」是三类不同证据，不可互相替代。",
        },
        "confidenceLegend": (old.get("confidenceLegend") or {
            "verified": "有明确字段 / 原始页面或一手数据支持",
            "estimated": "基于有限证据、社区讨论或近似模型，不是游戏原始公式",
            "missing": "无依据，不实现或明确不提供",
        }),
        "genericPools": (old.get("genericPools") or {}),
        "roster": {
            "boss": [b["k"] for b in bosses if b["category"] == "boss"],
            "goons": [b["k"] for b in bosses if b["category"] == "goons"],
            "special": [b["k"] for b in bosses if b["category"] == "special"],
            "event": [b["k"] for b in bosses if b["category"] == "event"],
            "elite": [e["k"] for e in elites],
        },
        "counts": {
            "bosses": len(bosses), "elites": len(elites),
            "withFollowers": sum(1 for b in bosses if b["followers"]),  # 有真实护卫血量表的
            "withDefaultPlates": sum(1 for b in bosses if b["equipment"]["defaultPlates"]),
            "unclassifiedLinks": len(unclassified), "unresolvedPages": len(unresolved),
        },
        "unresolved": unresolved,
        "unclassified": unclassified[:300],
        "bosses": bosses,
        "elites": elites,
    }
    write_json(OUT, doc)

    # 结构化审计：Boss → 实际装备/插板预设（供文档与人工复核，不含新数据）
    audit = {"generatedAt": doc["generatedAt"], "source": doc["source"]["method"],
             "legend": {"verified": "页面/预设直接给出", "estimated": "由默认预设顺序或名称映射推断",
                        "missing": "无依据"},
             "entities": []}
    for e in bosses + elites:
        eq = e["equipment"]
        titles = eq.get("titles") or {}
        def named(ids):
            return [{"id": i, "name": (local.get(i) or {}).get("n"), "title": titles.get(i),
                     "cl": (local.get(i) or {}).get("cl")} for i in ids or []]
        audit["entities"].append({
            "k": e["k"], "n": e["n"], "category": e["category"], "total": e["total"],
            "healthConfidence": e["healthConfidence"], "sourcePage": e["sourcePage"],
            "armor": named(eq.get("armor")), "helmets": named(eq.get("helmets")),
            "faces": named(eq.get("faces")), "platesListed": named(eq.get("plates")),
            "defaultArmor": eq.get("defaultArmor"),
            "defaultPlates": eq.get("defaultPlates"),
            "followers": [{"k": f["k"], "n": f["n"], "total": f.get("total"),
                           "healthConfidence": f.get("healthConfidence"),
                           "equipmentConfidence": f.get("equipmentConfidence")}
                          for f in (e.get("followers") or [])],
            "missing": e.get("missing"),
            "confidence": {"health": e["healthConfidence"], "equipment": eq.get("confidence"),
                           "combination": eq.get("combinationConfidence"),
                           "defaultPlates": (eq.get("defaultPlates") or {}).get("confidence", "missing")},
        })
    os.makedirs(os.path.dirname(LOADOUTS), exist_ok=True)
    write_json(LOADOUTS, audit)
    print("bosses=%d elites=%d followers=%d defaultPlates=%d unclassified=%d unresolved=%d"
          % (len(bosses), len(elites), doc["counts"]["withFollowers"],
             doc["counts"]["withDefaultPlates"], len(unclassified), len(unresolved)))
    for e in bosses + elites:
        dp = e["equipment"]["defaultPlates"] or {}
        print("  %-18s %-8s total=%-5d hpOK=%-5s armor=%-3d helm=%-2d face=%-2d front=%-24s back=%s"
              % (e["k"], e["category"], e["total"], e["healthConfidence"] == "verified",
                 len(e["equipment"]["armor"]), len(e["equipment"]["helmets"]),
                 len(e["equipment"]["faces"]), dp.get("front"), dp.get("back")))


if __name__ == "__main__":
    sys.exit(main())
