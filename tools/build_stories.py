# -*- coding: utf-8 -*-
"""R86 剧情系统数据构建器。

输入（均已离线缓存在仓库内，可重复构建）：
  build-cache/eftarkov/storyline-index.html
  build-cache/eftarkov/storyline-<slug>.html   eftarkov 剧情页（真实页面快照）
  data/task-points.json                        地图上的剧情点位（story-<storyId>-<objectiveId>）
输出：
  data/stories.json                            剧情线 / 步骤 / 分支 / 结局 / 前置

字段来源（与 db4tarkov 客户端 main.dart.js 的真实字段对齐，见 docs/r86-storyline/）：
  eftarkov  DOM data-obj-id / data-story-sort / data-choice-key / data-source-key / data-option-value
  db4tarkov Task.taskRequirements[{task,status}] / Task.storyVariable{variableId,compareMethod,value}
  db4tarkov trader.name === "Story"     → 剧情任务分组
  db4tarkov story_* 变量                → 结局标记（story_the_ticket_ending 等）

用法：python tools/build_stories.py
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "build-cache", "eftarkov")
OUT = os.path.join(ROOT, "data", "stories.json")

# eftarkov 剧情页快照：id → slug（抓取时间 2026-11-05）
PAGES = [
    ("6903d779fdfc4078740a4bd0", "they-are-already-here"),
    ("69052e18e680c2d3e3034d3a", "accidental-witness"),
    ("6900927ab7d28358f80b9421", "the-unheard"),
    ("68e784b7fa3f1fa3770094ba", "blue-fire"),
    ("68da33fe00868edcb6025ac4", "the-ticket"),
    ("68da36cf7cff54fc6109874a", "batya"),
    ("69d38381cea4b428690ea1d9", "boreas"),
    ("68cbd33676fe74b1e80bfd91", "tour"),
    ("68e3a35002661eb2d30ce387", "the-labyrinth"),
    ("68cbcdc4c964ab83cc0c928e", "falling-skies"),
]

# db4tarkov 剧情变量键（main.dart.js 中 story_* 字符串；仅记录有直接证据的）
STORY_KEYS = {
    "68cbcdc4c964ab83cc0c928e": "story_falling_skies",
    "68da33fe00868edcb6025ac4": "story_the_ticket",
    "68da36cf7cff54fc6109874a": "story_batya",
    "69d38381cea4b428690ea1d9": "story_boreas",
    "68e3a35002661eb2d30ce387": "story_the_labyrinth",
    "6903d779fdfc4078740a4bd0": "story_they_are_already_here",
    "69052e18e680c2d3e3034d3a": "story_accidental_witness",
    "68e784b7fa3f1fa3770094ba": "story_blue_fire",
    "68cbd33676fe74b1e80bfd91": "story_tour",
}

# db4tarkov 结局变量 → 结局值（main.dart.js: $.hP）
ENDING_VARS = {
    "story_the_ticket_ending": [
        ("survivor", "Survivor"),
        ("savior", "Savior"),
        ("fallen", "Fallen"),
        ("debtor", "Debtor"),
    ],
}
# 站点中文标签 → db4tarkov 结局键（站点的 data-option-value 顺序与标签顺序不一致，
# 以 db4tarkov 的 story_the_ticket_ending 四个值为准，按语义一一对应）。
ENDING_LABEL_KEYS = {
    "幸存者": "survivor",
    "救星": "savior",
    "陨落之人": "fallen",
    "旧债沉疴": "debtor",
}


def text(fragment):
    """HTML 片段 → 纯文本（保留 <br> 换行，压缩空白）。"""
    if not fragment:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", fragment)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join([ln for ln in lines if ln]).strip()


def attr(tag, name):
    m = re.search(r'%s="([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else ""


def parse_page(sid, slug):
    path = os.path.join(CACHE, "storyline-%s.html" % slug)
    s = open(path, encoding="utf-8", errors="replace").read()

    title = ""
    m = re.search(r"<title>(.*?)</title>", s, re.S)
    if m:
        title = text(m.group(1)).split(" - ")[0].strip()
    h1 = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
    if m:
        h1 = text(m.group(1))

    # 步骤：obj-block（data-story-sort 是站内排序号）
    steps = []
    parts = re.split(r'(?=<div class="obj-block storyline-objective)', s)
    for part in parts[1:]:
        nxt = part.find('<div class="obj-block storyline-objective', 10)
        block = part[:nxt] if nxt > 0 else part
        oid = attr(block[:400], "data-obj-id") or attr(block[:400], "id").replace("obj-", "")
        if not oid:
            continue
        tm = re.search(r'<h3 class="obj-title[^"]*">(.*?)</h3>', block, re.S)
        name = text(tm.group(1)) if tm else ""
        sort = attr(block[:400], "data-story-sort")
        steps.append({
            "id": oid,
            "order": int(sort) if sort.isdigit() else len(steps) + 1,
            "name": name,
        })
    steps.sort(key=lambda x: (x["order"], x["id"]))

    # 分支 / 结局选项：按 story-choice-card 解析（data-choice-key 或 data-source-key）
    choices = {}
    cards = re.split(r'(?=<div class="story-choice-card)', s)
    for card in cards[1:]:
        nxt = card.find('<div class="story-choice-card', 10)
        block = card[:nxt] if nxt > 0 else card
        head = block[:800]
        ckey = attr(head, "data-choice-key")
        sort_m = re.search(r'data-story-sort="(\d+)"', head)
        corder = int(sort_m.group(1)) if sort_m else 0
        tm = re.search(r"<strong>(.*?)</strong>", head, re.S)
        dm = re.search(r'story-choice-desc">(.*?)</div>', head, re.S)
        title = text(tm.group(1)) if tm else ""
        desc = text(dm.group(1)) if dm else ""

        options = []
        owner = sid
        src_key = ""
        for m in re.finditer(r'<button[^>]*class="story-choice-option[^"]*"(.*?)</button>', block, re.S):
            b = m.group(1)
            tag = b[:b.find(">")] if ">" in b else b
            value = attr(tag, "data-option-value")
            if not value:
                continue
            source = attr(tag, "data-source-key")
            if source:
                owner, src_key = (source.split("|") + [""])[:2]
            ot = re.search(r'story-choice-option-title">(.*?)</span>', b, re.S)
            od = re.search(r'story-choice-option-desc">(.*?)</span>', b, re.S)
            options.append({
                "value": value,
                "rawValue": value,
                "name": text(ot.group(1)) if ot else value,
                "desc": text(od.group(1)) if od else "",
            })
        if not options:
            continue
        role = "prerequisite" if src_key else "choice"
        if not src_key and ("结局" in title or "结局" in desc):
            role = "ending"
        if not ckey and not src_key:
            ckey = "choice-" + str(corder)
        rec_key = ckey if ckey else "__pre__" + owner + "|" + src_key
        rec = choices.get(rec_key)
        if not rec:
            rec = choices[rec_key] = {
                "key": ckey or src_key,
                "ownerStoryId": owner,
                "role": role,
                "title": title,
                "desc": desc,
                "order": corder,
                "options": [],
            }
        for o in options:
            if any(x["rawValue"] == o["rawValue"] for x in rec["options"]):
                continue
            rec["options"].append(o)
    # 选项顺序按页面出现顺序固定（value 顺序即站点顺序）

    # The Ticket 的结局变量（db4tarkov story_the_ticket_ending）→ 给结局选项补权威键。
    # 站点 data-option-value 的顺序与中文标签顺序不一致，这里按语义重新对齐并保留 rawValue。
    for rec in choices.values():
        if rec["role"] != "ending":
            continue
        for var, vals in ENDING_VARS.items():
            if sum(1 for o in rec["options"] if o["name"] in ENDING_LABEL_KEYS) >= 2:
                rec["variableId"] = var
                for o in rec["options"]:
                    o["endingKey"] = ENDING_LABEL_KEYS.get(o["name"], o["rawValue"].lower())
                    o["value"] = o["endingKey"]
        if "variableId" not in rec:
            for o in rec["options"]:
                o["value"] = o["rawValue"]

    # 前置剧情：data-source-key 指向其它剧情
    prereq = {}
    for rec in choices.values():
        if rec["role"] == "prerequisite" and rec["ownerStoryId"] != sid:
            prereq.setdefault(rec["ownerStoryId"], {
                "storyId": rec["ownerStoryId"],
                "choiceKey": rec["key"],
                "options": sorted({o["value"] for o in rec["options"]}),
            })
    # 文本里显式提到的「在剧情【X】中」也记为软前置（仅提示，不阻塞）
    note_refs = sorted(set(re.findall(r"剧情【([^】]+)】", text(s))))

    return {
        "id": sid,
        "slug": slug,
        "storyKey": STORY_KEYS.get(sid),
        "nameZh": h1 or title,
        "nameEn": title if re.search(r"[A-Za-z]", title) else h1,
        "steps": steps,
        "choices": sorted(choices.values(), key=lambda c: (c["role"] != "prerequisite", c["order"], c["key"])),
        "prerequisites": sorted(prereq.values(), key=lambda p: p["storyId"]),
        "noteRefs": note_refs,
        "sourcePage": "https://www.eftarkov.com/storyline/%s" % sid,
    }


def main():
    points = json.load(open(os.path.join(ROOT, "data", "task-points.json"), encoding="utf-8"))
    # storyId → {objId: {maps, points, objective}}
    point_index = {}
    # storyId → set(maps)
    story_maps = {}
    for map_key, mv in points.get("maps", {}).items():
        for grp in mv.get("stories", []):
            gid = grp.get("id", "")
            if not gid.startswith("story-"):
                continue
            body = gid[len("story-"):]
            sid = body[:24]
            obj = body[25:] if len(body) > 25 else ""
            if len(sid) != 24 or not re.match(r"^[0-9a-f]{24}$", sid):
                continue
            story_maps.setdefault(sid, set()).add(map_key)
            rec = point_index.setdefault(sid, {}).setdefault(obj, {
                "objective": grp.get("objective", ""),
                "name": grp.get("name", ""),
                "maps": set(),
                "points": 0,
            })
            rec["maps"].add(map_key)
            rec["points"] += len(grp.get("points", []))

    stories = []
    for sid, slug in PAGES:
        rec = parse_page(sid, slug)
        pmap = point_index.get(sid, {})
        rec["maps"] = sorted(story_maps.get(sid, set()))
        rec["stepCount"] = len(rec["steps"])
        rec["pointCount"] = sum(v["points"] for v in pmap.values())
        # task-points 的分组 id 有时只带 objectiveId 前 8 位 + 地图序号（如 6ab925ce8），
        # 因此先精确匹配完整 id，再按前 8 位匹配；同前缀的多个步骤只归给第一个（避免重复计数）。
        used_prefix = set()
        for st in rec["steps"]:
            p = pmap.get(st["id"])
            if not p:
                pref = st["id"][:8]
                for k, v in pmap.items():
                    if k == "unlock" or len(k) > 9:
                        continue
                    if k[:8] == pref and pref not in used_prefix:
                        p = v
                        used_prefix.add(pref)
                        st["mapMatch"] = "prefix"
                        break
            st["maps"] = sorted(p["maps"]) if p else []
            st["points"] = p["points"] if p else 0
        rec["unlockPoints"] = sorted(pmap.get("unlock", {}).get("maps", [])) if "unlock" in pmap else []
        rec["unlockNote"] = pmap.get("unlock", {}).get("objective", "") if "unlock" in pmap else ""
        stories.append(rec)

    # 数据缺口：不隐藏，交给前端「数据缺口 / 说明」折叠块如实展示
    gaps = []
    orphan = 0
    for map_key, mv in points.get("maps", {}).items():
        for grp in mv.get("stories", []):
            gid = grp.get("id", "")
            sid = gid[len("story-"):][:24] if gid.startswith("story-") else ""
            if len(sid) != 24 or not re.match(r"^[0-9a-f]{24}$", sid):
                orphan += 1
    if orphan:
        gaps.append({"type": "orphan-points", "message":
                     "data/task-points.json 中有 %d 组剧情点无法归属到剧情线（id 形如 story-story-obj），"
                     "地图上仍会显示，但没有可跳转的剧情详情。" % orphan})
    for rec in stories:
        if not rec["storyKey"]:
            gaps.append({"type": "no-story-key", "message":
                         "%s（%s）在 db4tarkov 客户端里没有找到 story_* 变量键，分支结局按站点选项展示。"
                         % (rec["nameZh"], rec["id"])})
        no_map = [s for s in rec["steps"] if not s["maps"]]
        if no_map:
            gaps.append({"type": "step-without-map", "message":
                         "%s：%d/%d 个步骤未匹配到地图点位（文本步骤，或来源只给了 objectiveId 前 8 位无法唯一对应）。"
                         % (rec["nameZh"], len(no_map), len(rec["steps"]))})
        if not rec["steps"]:
            gaps.append({"type": "no-steps", "message":
                         "%s（%s）没有解析到步骤，剧情树为空。" % (rec["nameZh"], rec["id"])})

    # 顺序：按站点索引页出现顺序（若快照存在）
    order = {}
    try:
        idx = open(os.path.join(CACHE, "storyline-index.html"), encoding="utf-8", errors="replace").read()
        seen = []
        for m in re.finditer(r'href="/storyline/([0-9a-f]{24})"', idx):
            if m.group(1) not in seen:
                seen.append(m.group(1))
        order = {sid: i + 1 for i, sid in enumerate(seen)}
    except IOError:
        pass
    for i, rec in enumerate(stories):
        rec["order"] = order.get(rec["id"], 100 + i)

    doc = {
        "schema": 1,
        "generatedAt": "2026-11-05T22:00:00+08:00",
        "source": {
            "site": "eftarkov.com",
            "pages": ["https://www.eftarkov.com/storyline/%s" % sid for sid, _ in PAGES],
            "db4tarkov": "main.dart.js（docs/r39-live-price/main.dart.js.full）",
            "points": "data/task-points.json",
        },
        "counts": {
            "stories": len(stories),
            "steps": sum(len(s["steps"]) for s in stories),
            "choices": sum(len(s["choices"]) for s in stories),
            "endings": sum(1 for s in stories for c in s["choices"] if c["role"] == "ending"),
        },
        "dataGaps": gaps,
        "stories": stories,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("stories:", len(stories))
    for rec in stories:
        print(" %-24s %-28s steps=%2d points=%3d choices=%d pre=%d" % (
            rec["id"], rec["nameZh"], rec["stepCount"], rec["pointCount"],
            len(rec["choices"]), len(rec["prerequisites"])))
    print("->", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    sys.exit(main())
