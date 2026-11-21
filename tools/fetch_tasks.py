# -*- coding: utf-8 -*-
"""EFT 任务数据抓取与标准化（R19.23：三模式）。

数据源
------
* 结构：https://json.tarkov.dev/{upstream}/tasks         （upstream = regular / pve / pvp-season）
* 中文：https://json.tarkov.dev/{upstream}/tasks_zh      （扁平字典：翻译键 → 中文）
* 商人：https://json.tarkov.dev/{upstream}/traders + traders_zh
* 赛季：https://json.tarkov.dev/pvp-season/season + season_zh（赛季 id / 起止时间 / 赛季技能）
* 本地：data/maps.json（地图中文名）、data/items.json（物品中文名）

模式映射（本项目 key → 上游 gameMode）
--------------------------------------
    regular → regular       界面 PvP（常规）
    pve     → pve           界面 PvE
    pvps    → pvp-season    界面 PvPS（赛季服）

上游 `json.tarkov.dev/endpoints` 的 gameModes 字段直接给出 regular / pve / pvp-season，
因此 PvPS **不是**把 PvP 改名：它走独立端点、独立任务集（当前快照为 PvP 的真子集）。

为什么不用 GraphQL：静态 JSON 与项目既有 `tools/fetch_data.py` 同源同许可，
且离线可复核（原始快照落 data/tasks/raw/）。

数据目录
--------
data/tasks/tasks.<mode>.json   标准化任务（含目标 / 前置 / 奖励 / 条件 / 攻略 / 跨模式标记）
data/tasks/guides.<mode>.json  攻略正文（与任务分离，便于单独校对/替换）
data/tasks/traders.json        商人表（中英名 + 图标 + 各模式任务数）
data/tasks/season.json         赛季元信息（id / 起止时间 / 赛季技能，含中文说明）
data/tasks/index.json          元信息：模式、数量、来源、生成时间、覆盖率、跨模式归属
data/tasks/sources.json        来源 URL / 许可 / sha256 / 抓取时间 / 失败原因

用法
----
    python tools/fetch_tasks.py              # 联网抓取（默认走 http://127.0.0.1:7896 代理）
    python tools/fetch_tasks.py --offline    # 只用 data/tasks/raw/ 里的快照重建
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TASKS_DIR = os.path.join(DATA, "tasks")
RAW_DIR = os.path.join(TASKS_DIR, "raw")
PROXY = os.environ.get("EFTMAP_PROXY", "http://127.0.0.1:7896")
MODES = ("regular", "pve", "pvps")
# 本项目模式 key → 上游 gameMode 路径段（来自 json.tarkov.dev/endpoints 的 gameModes）
UPSTREAM = {"regular": "regular", "pve": "pve", "pvps": "pvp-season"}
MODE_LABEL = {"regular": "PvP（常规）", "pve": "PvE", "pvps": "PvPS（赛季服）"}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eft-interactive-map/tasks"}


# ---------------------------------------------------------------- 抓取
def _fetch(url: str, timeout: int = 180) -> bytes:
    """优先走本地代理，失败再直连（与 fetch_data.py 同策略）。"""
    last = None
    for proxy in (PROXY, None):
        try:
            handlers = []
            if proxy:
                handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
            else:
                handlers.append(urllib.request.ProxyHandler({}))
            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers=UA)
            with opener.open(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:            # noqa: BLE001 - 记录后换下一种
            last = exc
    raise RuntimeError("抓取失败 %s：%s" % (url, last))


def _valid_json(blob: bytes) -> bool:
    try:
        json.loads(blob.decode("utf-8"))
        return True
    except Exception:            # noqa: BLE001 - 坏响应一律当失败，绝不覆盖旧快照
        return False


def fetch_raw(offline: bool = False) -> list[dict]:
    """抓取三模式原始快照。

    失败策略（任务书 §十）：
      * 某个端点抓取失败 / 返回非法 JSON → **不覆盖**已有快照，记录 error 后继续用旧快照；
      * 旧快照也不存在 → 该模式视为不可用，任务数据整体中止（绝不写空文件）。
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    jobs = []
    for mode in MODES:
        up = UPSTREAM[mode]
        jobs.append((mode, "tasks", "https://json.tarkov.dev/%s/tasks" % up, True))
        jobs.append((mode, "tasks_zh", "https://json.tarkov.dev/%s/tasks_zh" % up, True))
    jobs.append(("regular", "traders", "https://json.tarkov.dev/regular/traders", True))
    jobs.append(("regular", "traders_zh", "https://json.tarkov.dev/regular/traders_zh", True))
    jobs.append(("pvps", "traders", "https://json.tarkov.dev/pvp-season/traders", False))
    jobs.append(("pvps", "season", "https://json.tarkov.dev/pvp-season/season", False))
    jobs.append(("pvps", "season_zh", "https://json.tarkov.dev/pvp-season/season_zh", False))
    jobs.append(("regular", "maps_zh", "https://json.tarkov.dev/regular/maps_zh", False))

    sources = []
    for mode, kind, url, required in jobs:
        path = os.path.join(RAW_DIR, "%s.%s.json" % (kind, mode))
        error = None
        if not offline:
            try:
                blob = _fetch(url)
                if not _valid_json(blob):
                    raise RuntimeError("返回内容不是合法 JSON（%d 字节）" % len(blob))
                with open(path, "wb") as fh:
                    fh.write(blob)
                print("fetched %-8s %-10s %8.1f KB" % (mode, kind, len(blob) / 1024.0))
            except Exception as exc:       # noqa: BLE001 - 失败保留旧快照
                error = str(exc)
                print("FAILED  %-8s %-10s %s" % (mode, kind, error))
        if not os.path.exists(path):
            if required or error is None:
                raise SystemExit("缺少原始快照：%s（联网抓取失败：%s）" % (path, error or "未抓取"))
            print("SKIP    %-8s %-10s 无快照且抓取失败，跳过（可选数据）" % (mode, kind))
            continue
        blob = open(path, "rb").read()
        rec = {
            "endpoint": kind,
            "mode": mode,
            "url": url,
            "license": "tarkov.dev 社区公开数据（非官方）",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(os.path.getmtime(path))),
        }
        if error:
            rec["error"] = error
            rec["stale"] = True
        sources.append(rec)
    return sources


# ---------------------------------------------------------------- 辅助
def load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def localize(table: dict, key, fallback=None):
    """tasks_zh 是扁平字典：键就是英文占位串本身。"""
    if key and isinstance(table.get(key), str) and table[key].strip():
        return table[key]
    return fallback if fallback is not None else key


def map_index() -> dict:
    """地图 id → 中文名。

    优先 data/maps.json（与地图页显示完全一致）；缺少的新图用上游 maps_zh 补齐
    （例如中心区 21+、码头），再不行才回退 id —— 绝不臆造名字。
    """
    out = {}
    path = os.path.join(DATA, "maps.json")
    if os.path.exists(path):
        for m in load_json(path).get("maps") or []:
            if m.get("id"):
                out[m["id"]] = {"name": m.get("name") or m.get("key") or m["id"],
                                "key": m.get("key") or ""}
    zh_path = os.path.join(RAW_DIR, "maps_zh.regular.json")
    if os.path.exists(zh_path):
        zh = load_json(zh_path)["data"]
        for key, value in zh.items():
            if key.endswith(" Name"):
                mid = key[: -len(" Name")]
                if mid not in out and isinstance(value, str) and value.strip():
                    out[mid] = {"name": value, "key": ""}
    return out


def item_index() -> dict:
    out = {}
    path = os.path.join(DATA, "items.json")
    if not os.path.exists(path):
        return out
    for iid, rec in (load_json(path).get("items") or {}).items():
        out[iid] = rec.get("n") or iid
    return out


# 上游中文翻译偶尔缺失（当前仅 1 条）：人工补译，并在字段里标明来源
TASK_NAME_OVERRIDES = {
    "Make ULTRA Great Again": "让 ULTRA 再次伟大",
    "Half-Empty": "半空",
}

# 上游 count 是「整个目标合计数量」；只有单物品目标能一一对应到图标角标
ITEM_COUNT_TYPES = ("giveItem", "findItem", "plantItem", "sellItem")

OBJECTIVE_KIND = {
    "visit": "到达位置",
    "mark": "安放标记",
    "shoot": "击杀",
    "findItem": "找到物品",
    "findQuestItem": "找到任务物品",
    "giveItem": "上交物品",
    "giveQuestItem": "上交任务物品",
    "plantItem": "安放物品",
    "plantQuestItem": "安放任务物品",
    "extract": "撤离",
    "buildWeapon": "组装武器",
    "useItem": "使用物品",
    "sellItem": "出售物品",
    "traderLevel": "商人等级",
    "traderStanding": "商人声望",
    "taskStatus": "任务状态",
    "skill": "技能等级",
    "experience": "经验值",
    "globalVariable": "全局条件",
    "dialogue": "对话",
}


# 上游中文翻译偶尔直接返回英文（当前 5 条）：人工补译，避免中文界面里冒出整句英文
OBJECTIVE_TEXT_OVERRIDES = {
    "You must not kill Rogues or The Goons on Lighthouse while the task is active":
        "任务进行期间不得击杀灯塔的 Rogues 或 The Goons",
    "Find the item: 6-STEN-140-M military battery": "找到物品：6-STEN-140-M 军用电池",
    "Eliminate PMC operatives": "消灭 PMC 干员",
}


def obj_desc(o: dict, zh: dict, items: dict) -> str:
    """目标中文描述：优先上游中文翻译，缺失/仍是英文时按类型拼一句可读中文。"""
    key = o.get("description")
    text = localize(zh, key, None)
    if text and text != key:
        if re.search(r"[\u4e00-\u9fff]", text):
            return text
        override = OBJECTIVE_TEXT_OVERRIDES.get(text)
        if override:
            return override
    kind = OBJECTIVE_KIND.get(o.get("type"), o.get("type") or "目标")
    bits = [kind]
    if o.get("count"):
        bits.append("×%s" % o["count"])
    names = [items.get(i, i) for i in (o.get("items") or [])]
    if names:
        bits.append("（%s）" % "、".join(names[:3]) + ("…" if len(names) > 3 else ""))
    return "".join(bits)


ZONE_MAP_KEYS = ("maps",)


def _flat_ids(value) -> list[str]:
    """上游部分字段是「列表套列表」（例如 requiredKeys / usingWeaponMods）。"""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    return out


def _names(value, items: dict) -> str:
    return "、".join(items.get(i, i) for i in _flat_ids(value))


def obj_constraints(o: dict, items: dict) -> list[str]:
    """把真实限制翻译成人话（只依据字段，不猜）。"""
    out = []
    if o.get("foundInRaid"):
        out.append("物品必须战局内找到（FIR）")
    if o.get("wearing"):
        out.append("必须穿戴：%s" % _names(o["wearing"], items))
    if o.get("notWearing"):
        out.append("不得穿戴：%s" % _names(o["notWearing"], items))
    if o.get("usingWeapon"):
        out.append("使用指定武器：%s" % _names(o["usingWeapon"], items))
    if o.get("usingWeaponMods"):
        out.append("武器需装：%s" % _names(o["usingWeaponMods"], items))
    if o.get("distance"):
        out.append("距离 ≤ %s 米" % o["distance"].get("value"))
    if o.get("bodyParts"):
        out.append("部位：%s" % "、".join(o["bodyParts"]))
    if o.get("shotType"):
        out.append("射击方式：%s" % o["shotType"])
    if o.get("timeFromHour") is not None or o.get("timeUntilHour") is not None:
        out.append("时间窗 %s–%s 时" % (o.get("timeFromHour"), o.get("timeUntilHour")))
    if o.get("minDurability") is not None:
        out.append("最低耐久 %s" % o["minDurability"])
    if o.get("maxDurability") is not None:
        out.append("最高耐久 %s" % o["maxDurability"])
    if o.get("requiredKeys"):
        out.append("需要钥匙：%s" % _names(o["requiredKeys"], items))
    if o.get("exitName"):
        out.append("撤离点：%s" % o["exitName"])
    if o.get("status"):
        out.append("任务状态需为：%s" % "、".join(o["status"]))
    return out


def obj_maps(o: dict, maps: dict) -> list[str]:
    ids = list(o.get("maps") or [])
    if o.get("map"):
        ids.append(o["map"])
    for z in o.get("zones") or []:
        if z.get("map"):
            ids.append(z["map"])
    names = []
    for mid in ids:
        name = (maps.get(mid) or {}).get("name") or mid
        if name not in names:
            names.append(name)
    return names


def norm_objectives(raw: list, zh: dict, items: dict, maps: dict) -> list[dict]:
    out = []
    for o in raw or []:
        item_ids = _flat_ids(o.get("items"))
        # 单物品目标的 count 就是该物品件数（giveItem/findItem/plantItem/sellItem）；
        # 多物品目标是「列表内任一/某类合计 N 件」（例如 52 种医疗任交 3 件），
        # 逐图标写 N 会误导，故只保留目标级 count，不写到每个 item 上。
        item_count = (o.get("count") if len(item_ids) == 1
                      and o.get("type") in ITEM_COUNT_TYPES else None)
        out.append({
            "id": o.get("id"),
            "type": o.get("type"),
            "kindZh": OBJECTIVE_KIND.get(o.get("type"), o.get("type")),
            "descZh": obj_desc(o, zh, items),
            "descEn": o.get("description"),
            "optional": bool(o.get("optional")),
            "count": o.get("count"),
            "items": [{"id": i, "name": items.get(i, i), "count": item_count}
                      for i in item_ids],
            "item": ({"id": o["item"], "name": items.get(o["item"], o["item"])} if o.get("item") else None),
            "questItem": ({"id": o["questItem"], "name": items.get(o["questItem"], o["questItem"])}
                          if o.get("questItem") else None),
            "maps": obj_maps(o, maps),
            "constraints": obj_constraints(o, items),
            "zones": [{
                "id": z.get("id"),
                "mapId": z.get("map"),
                "mapName": (maps.get(z.get("map")) or {}).get("name") or z.get("map"),
                "position": z.get("position"),
                "outline": z.get("outline") or [],
                "top": z.get("top"), "bottom": z.get("bottom"),
            } for z in (o.get("zones") or [])],
            "raw": {k: v for k, v in o.items()
                    if k in ("distance", "bodyParts", "shotType", "wearing", "notWearing",
                             "usingWeapon", "usingWeaponMods", "foundInRaid", "exitName",
                             "timeFromHour", "timeUntilHour", "minDurability", "maxDurability",
                             "requiredKeys", "skill", "level", "trader", "traders", "task",
                             "status", "value", "compareMethod", "globalVariable", "targetNames",
                             "possibleLocations", "useAny", "containsAll", "markerItem")},
        })
    return out


def norm_rewards(raw: dict, items: dict, traders: dict) -> dict:
    raw = raw or {}
    return {
        "items": [{"id": it.get("item"), "name": items.get(it.get("item"), it.get("item")),
                   "count": it.get("count")} for it in (raw.get("items") or [])],
        "traderStanding": [{"traderId": s.get("trader"),
                            "traderZh": (traders.get(s.get("trader")) or {}).get("nameZh")
                                        or (traders.get(s.get("trader")) or {}).get("nameEn"),
                            "standing": s.get("standing")} for s in (raw.get("traderStanding") or [])],
        "offerUnlock": raw.get("offerUnlock") or [],
        "skillLevelReward": raw.get("skillLevelReward") or [],
        "traderUnlock": raw.get("traderUnlock") or [],
        "craftUnlock": raw.get("craftUnlock") or [],
        "achievement": raw.get("achievement") or [],
        "traderDialogueUnlock": raw.get("traderDialogueUnlock") or [],
        "locationUnlock": raw.get("locationUnlock") or [],
        "customization": raw.get("customization") or [],
    }


def norm_conditions(task: dict, traders: dict) -> list[dict]:
    """非任务型前置条件：等级 / 忠诚 / 声望 / 阵营 / 技能 / 对话 / 全局变量。"""
    out = []
    if task.get("minPlayerLevel"):
        out.append({"kind": "playerLevel", "text": "角色等级 ≥ %s" % task["minPlayerLevel"],
                    "value": task["minPlayerLevel"]})
    fac = task.get("factionName")
    if fac and fac != "Any":
        out.append({"kind": "faction", "text": "阵营：%s（BEAR/USEC）" % fac, "value": fac})
    for r in task.get("traderRequirements") or []:
        tz = (traders.get(r.get("trader")) or {}).get("nameZh") or r.get("trader")
        if r.get("requirementType") == "level":
            out.append({"kind": "traderLevel", "text": "%s 忠诚等级 ≥ %s" % (tz, r.get("value")),
                        "traderId": r.get("trader"), "value": r.get("value")})
        elif r.get("requirementType") == "reputation":
            out.append({"kind": "traderStanding", "text": "%s 声望 ≥ %s" % (tz, r.get("value")),
                        "traderId": r.get("trader"), "value": r.get("value")})
        else:
            out.append({"kind": r.get("requirementType") or "trader",
                        "text": "%s 条件 %s %s" % (tz, r.get("compareMethod"), r.get("value"))})
    for r in task.get("otherRequirements") or []:
        kind = r.get("type")
        if kind == "skill":
            out.append({"kind": "skill", "text": "技能 %s 等级 ≥ %s" % (r.get("skill"), r.get("level")),
                        "raw": r})
        elif kind == "dialogue":
            names = [((traders.get(t) or {}).get("nameZh") or t) for t in (r.get("traders") or [])]
            out.append({"kind": "dialogue", "text": "与 %s 完成对话" % "、".join(names), "raw": r})
        elif kind == "globalVariable":
            out.append({"kind": "globalVariable", "text": "剧情变量条件（上游 globalVariable）", "raw": r})
        elif kind == "level":
            out.append({"kind": "playerLevel", "text": "角色等级 ≥ %s" % r.get("level"), "raw": r})
        else:
            out.append({"kind": kind or "other", "text": "其他开放条件（%s）" % (kind or "unknown"),
                        "raw": r})
    return out


def english_name(task: dict, known_en: dict) -> tuple:
    """返回 (英文显示名, 来源)。

    上游 `tasks` 静态 JSON 的 name 是「<id> name」占位串（英文 locale 表全为空），
    因此依次尝试：项目 items.json 的 tasks 表（真实英文名）→ wiki 链接 slug 还原。
    """
    tid = task.get("id")
    real = known_en.get(tid)
    if real and not re.match(r"^[0-9a-f]{24} name$", real):
        # items.json 里个别条目也带 URL 编码（例如 "Tickets%2C Please"）：统一解码
        return (urllib.request.unquote(real) if "%" in real else real), "items.json"
    link = task.get("wikiLink") or ""
    slug = link.rsplit("/", 1)[-1] if link else ""
    if slug:
        # wiki slug 是 URL 编码片段（%27 / %2C / %E2%80%99 等）：整段解码，避免英文名里冒出 %2C
        pretty = urllib.request.unquote(slug).replace("_", " ")
        return pretty.strip(), "wiki-slug"
    return "", "none"


def guide_for(task: dict, objectives: list, conditions: list, maps: dict,
              items: dict, follow_ups: list, peers: list) -> dict:
    """按真实字段生成结构化攻略（不改事实、不编坐标）。

    status:
      generated —— 由上游任务数据派生（默认，全部可复核）
      missing   —— 目标数据为空，无法成文
    """
    real = [o for o in objectives if not o["optional"]]
    opt = [o for o in objectives if o["optional"]]
    if not real and not opt:
        return {"status": "missing", "overview": "", "prep": [], "route": [],
                "steps": [], "notes": [], "parallel": [], "afterDone": []}

    map_names = []
    for o in objectives:
        for m in o["maps"]:
            if m not in map_names:
                map_names.append(m)

    # 概览
    kinds = []
    for o in real:
        if o["kindZh"] not in kinds:
            kinds.append(o["kindZh"])
    where = "、".join(map_names) if map_names else "多张地图"
    # R19.25：商人名统一用游戏内英文原名（traderEn），句子其余部分仍是中文
    overview = "由 %s 发布，在 %s 完成：%s。" % (
        task.get("traderEn") or "未知商人", where, "、".join(kinds) if kinds else "按目标推进")

    # 准备清单：只列数据能确认的（数量、候选、钥匙、任务物品）
    prep = []
    for o in objectives:
        cnt = o.get("count") or 1
        names = [it["name"] for it in o["items"]]
        if o["type"] in ("giveItem", "giveQuestItem") and names:
            if len(names) > 1:
                prep.append("需上交 %s 件（以下任一/组合）：%s" % (cnt, "、".join(names[:6])
                                                               + ("…" if len(names) > 6 else "")))
            else:
                prep.append("需上交 %s ×%s" % (names[0], cnt))
        elif o["type"] in ("plantItem", "plantQuestItem") and names:
            prep.append("需携带并安放 %s ×%s" % ("、".join(names), cnt))
        elif o["type"] in ("findItem", "findQuestItem") and names:
            prep.append("需找到 %s ×%s" % ("、".join(names), cnt))
        if o.get("questItem"):
            prep.append("任务物品：%s" % o["questItem"]["name"])
        for c in o["constraints"]:
            if c.startswith("需要钥匙"):
                prep.append(c)
    prep = list(dict.fromkeys(prep))

    # 路线
    route = []
    for m in map_names:
        zone_ids = [z["id"] for o in objectives for z in o["zones"] if z["mapName"] == m]
        route.append({"map": m, "zones": zone_ids[:12],
                      "text": "在「%s」完成 %d 项目标" % (m, sum(1 for o in real if m in o["maps"]))
                              + ("，目标点：%s" % "、".join(zone_ids[:4]) if zone_ids else "")})

    # 步骤
    steps = []
    for i, o in enumerate(objectives, 1):
        line = {"index": i, "type": o["type"], "kindZh": o["kindZh"], "text": o["descZh"],
                "optional": o["optional"], "maps": o["maps"], "constraints": o["constraints"],
                "count": o["count"], "items": [it["name"] for it in o["items"]]}
        steps.append(line)

    # 注意事项（只写数据支持的）
    notes = []
    if any("FIR" in c for o in objectives for c in o["constraints"]):
        notes.append("部分物品要求战局内找到（FIR），死亡后掉落的物品无效，建议放安全容器。")
    if any("撤离" in o["kindZh"] or o.get("type") == "extract" for o in objectives):
        notes.append("目标包含撤离类条件，注意撤离点开放时间与携带限制。")
    if any(o["zones"] for o in objectives):
        notes.append("目标区域为上游标注的矩形范围，实际位置以游戏内地形为准。")
    if any(o["optional"] for o in objectives):
        notes.append("含可选目标（经验值加成），不影响任务完成判定。")
    if task.get("restartable"):
        notes.append("该任务可重新接取，失败后可再次尝试。")
    if any(c["kind"] == "faction" for c in conditions):
        notes.append("该任务有阵营限制，BEAR/USEC 仅一方可接。")
    if task.get("availableDelaySecondsMin"):
        # availableDelaySeconds 是「**可接取**之前的最短等待」，不是「接取后等交付」：
        # 上游语义 = 前置条件（前置任务/等级）满足后，还要再等这么久才刷出这个任务。
        # 早期版本写成「接取后需等待…才可完成/交付」，把前置等待说成了交付等待，属于语义错误。
        notes.append("前置条件满足后需再等待约 %d 分钟才可接取此任务。" % (task["availableDelaySecondsMin"] // 60))
    if opt:
        notes.append("可选目标 %d 项：%s" % (len(opt), "、".join(o["descZh"] for o in opt[:3])))

    after = []
    if follow_ups:
        after.append("后续任务 %d 个：%s" % (len(follow_ups), "、".join(f["nameZh"] for f in follow_ups[:5])))
    if any(o["type"] in ("giveItem", "giveQuestItem") for o in objectives):
        after.append("上交类目标需回到对应商人处提交（部分任务需在战局内交付）。")

    return {
        "status": "generated",
        "source": "tarkov.dev 任务数据（objectives/zones/requirements 字段派生）",
        "overview": overview,
        "prep": prep,
        "route": route,
        "steps": steps,
        "notes": notes,
        "parallel": peers,
        "afterDone": after,
    }


# ---------------------------------------------------------------- 标准化
def normalize(mode: str, raw: dict, zh: dict, traders: dict, maps: dict, items: dict,
              curated: dict, known_en: dict | None = None,
              presence: dict | None = None) -> dict:
    presence = presence or {}
    tasks_raw = raw["data"]["tasks"]
    out = {}
    guides = {}
    for tid, t in tasks_raw.items():
        trader_id = t.get("trader")
        tz = traders.get(trader_id) or {}
        name_en = t.get("name")
        name_zh = localize(zh, name_en, None)
        name_zh_source = "upstream"
        # 上游中文表偶尔把英文原样返回（值里没有汉字）→ 视为未翻译，走人工补译
        if not name_zh or name_zh == name_en or not re.search(r"[\u4e00-\u9fff]", name_zh):
            override = (TASK_NAME_OVERRIDES.get(name_zh) or TASK_NAME_OVERRIDES.get(name_en)
                        or TASK_NAME_OVERRIDES.get(t.get("normalizedName")))
            if override:
                name_zh, name_zh_source = override, "manual"
            else:
                name_zh = "%s（未翻译）" % (t.get("normalizedName") or tid)
                name_zh_source = "missing"

        prereq = []
        for r in t.get("taskRequirements") or []:
            statuses = list(r.get("status") or [])
            prereq.append({"taskId": r.get("task"), "statuses": statuses,
                           "logic": "or" if len(statuses) > 1 else "all"})
        failed_req = []
        for fc in t.get("failConditions") or []:
            if fc.get("type") == "taskStatus":
                failed_req.append({"taskId": fc.get("task"), "statuses": fc.get("status") or [],
                                   "descZh": localize(zh, fc.get("description"), fc.get("description"))})

        objectives = norm_objectives(t.get("objectives"), zh, items, maps)
        conditions = norm_conditions(t, traders)
        en_name, en_source = english_name(t, known_en or {})
        # 跨模式归属：任务在哪些模式里真实存在（按上游任务 ID 判定，不按名称合并）
        modes_have = sorted(presence.get(tid) or {mode}, key=lambda m: MODES.index(m)
                            if m in MODES else 99)
        rec = {
            "id": tid,
            "nameZh": name_zh,
            "nameZhSource": name_zh_source,
            "nameEn": name_en,
            "englishName": en_name,
            "englishSource": en_source,
            "normalizedName": t.get("normalizedName"),
            "traderId": trader_id,
            "traderZh": tz.get("nameZh") or tz.get("nameEn") or trader_id,
            "traderEn": tz.get("nameEn") or "",
            "traderImg": tz.get("img") or "",
            "minLevel": t.get("minPlayerLevel") or 0,
            "gameMode": mode,
            # 上游自带的 gameMode 列表（当前仅 4+1 条任务有值）——只做展示，不做判定
            "upstreamGameModes": t.get("gameMode") or [],
            "modeScope": "all" if len(modes_have) == len(MODES) else modes_have,
            "onlyInModes": [] if len(modes_have) == len(MODES) else modes_have,
            "seasonOnly": modes_have == ["pvps"],
            "taskType": t.get("taskType") or ("story" if t.get("isStoryTask") else "regular"),
            "map": (maps.get(t.get("map")) or {}).get("name") if t.get("map") else None,
            "mapId": t.get("map"),
            "maps": sorted({m for o in objectives for m in o["maps"]}),
            "faction": t.get("factionName") or "Any",
            "kappaRequired": bool(t.get("kappaRequired")),
            "lightkeeperRequired": bool(t.get("lightkeeperRequired")),
            "restartable": bool(t.get("restartable")),
            "experience": t.get("experience") or 0,
            "wikiLink": t.get("wikiLink"),
            "taskImageLink": t.get("taskImageLink"),
            "prerequisites": prereq,
            "failedConditions": failed_req,
            "conditions": conditions,
            "objectives": objectives,
            "rewards": norm_rewards(t.get("finishRewards"), items, traders),
            "startRewards": norm_rewards(t.get("startRewards"), items, traders),
            "failureOutcome": t.get("failureOutcome") or {},
            "neededKeys": t.get("neededKeys") or [],
            "availableDelaySecondsMin": t.get("availableDelaySecondsMin"),
            "followUps": [],          # 反向索引，稍后填
        }
        rec["guide"] = curated.get(tid) or None
        out[tid] = rec

    # 反向索引 + 并行建议（同图、同为未完成前置链上的任务）
    by_map = {}
    for tid, rec in out.items():
        for m in rec["maps"]:
            by_map.setdefault(m, []).append(tid)
    for tid, rec in out.items():
        fus = []
        for other_id, other in out.items():
            for p in other["prerequisites"]:
                if p["taskId"] == tid:
                    fus.append(other_id)
                    break
        rec["followUps"] = sorted(set(fus))
        peers = []
        for m in rec["maps"]:
            for pid in by_map.get(m, []):
                if pid != tid and pid not in peers and len(peers) < 6:
                    peers.append(pid)
        guide = guide_for(rec, rec["objectives"], rec["conditions"], maps, items,
                          [{"id": f, "nameZh": out[f]["nameZh"]} for f in rec["followUps"] if f in out],
                          [{"id": p, "nameZh": out[p]["nameZh"]} for p in peers if p in out])
        if tid in curated:
            guide.update({"status": "curated", "source": curated[tid].get("source", ""),
                          "notes": list(dict.fromkeys(curated[tid].get("notes", []) + guide["notes"]))})
        guides[tid] = guide

    # 引用完整性清理（引用不存在于同模式的任务时保留但标记）
    for rec in out.values():
        rec["prerequisites"] = [p for p in rec["prerequisites"] if p["taskId"] in out]
    for rec in out.values():
        rec["followUps"] = [f for f in rec["followUps"] if f in out]
    return out, guides


def known_english() -> dict:
    """items.json 里的任务英文名表（125 条，随物品资料库一起下发）。"""
    path = os.path.join(DATA, "items.json")
    if not os.path.exists(path):
        return {}
    return (load_json(path).get("tasks") or {})


def build(mode: str, sources: list, maps: dict, items: dict, curated: dict,
          known_en: dict | None = None, presence: dict | None = None) -> dict:
    raw = load_json(os.path.join(RAW_DIR, "tasks.%s.json" % mode))
    zh = load_json(os.path.join(RAW_DIR, "tasks_zh.%s.json" % mode))["data"]
    traders_raw = load_json(os.path.join(RAW_DIR, "traders.json"))["data"]
    traders_zh = load_json(os.path.join(RAW_DIR, "traders_zh.json"))["data"]

    # 商人名：上游 name 是占位串（"<id> Nickname"），中文也只有 Description，
    # 因此规范英文名 + 中文名统一由 data/i18n/traders.json 维护（按 normalizedName 匹配）。
    term_path = os.path.join(DATA, "i18n", "traders.json")
    terms = (load_json(term_path).get("traders") if os.path.exists(term_path) else {}) or {}
    traders = {}
    for tid, t in traders_raw.items():
        slug = (t.get("normalizedName") or "").lower()
        term = terms.get(slug) or {}
        name_en = term.get("nameEn") or (slug.replace("-", " ").title() or tid)
        traders[tid] = {
            "id": tid,
            "nameEn": name_en,
            "nameZh": term.get("nameZh") or name_en,
            "nameZhNote": term.get("note") or "",
            "normalizedName": slug,
            "img": t.get("imageLink") or "",
            "localIcon": "assets/icons-traders/%s.svg" % slug,
            "descriptionZh": localize(traders_zh, "%s Description" % tid, ""),
        }

    tasks, guides = normalize(mode, raw, zh, traders, maps, items, curated, known_en, presence)

    # 商人统计
    counts = {}
    for rec in tasks.values():
        counts[rec["traderId"]] = counts.get(rec["traderId"], 0) + 1
    for tid, t in traders.items():
        t.setdefault("taskCounts", {})[mode] = counts.get(tid, 0)

    return {"mode": mode, "modeLabel": MODE_LABEL[mode], "traders": traders,
            "tasks": tasks, "guides": guides, "sources": sources}


def season_meta() -> dict | None:
    """赛季元信息：id / 起止时间 / 赛季技能（中文说明来自 season_zh）。

    上游 name 是占位串（"<id> name"）且中文表里没有对应键，因此**不编名字**：
    nameZh 留空，前端显示为「当前赛季（未命名）」并给出起止时间。
    """
    path = os.path.join(RAW_DIR, "season.pvps.json")
    if not os.path.exists(path):
        return None
    raw = load_json(path)
    data = raw.get("data") or {}
    zh = {}
    zh_path = os.path.join(RAW_DIR, "season_zh.pvps.json")
    if os.path.exists(zh_path):
        zh = load_json(zh_path).get("data") or {}

    def perk(p):
        pid = p.get("id")
        return {
            "id": pid,
            "nameEn": "" if str(p.get("name") or "").endswith(" name") else p.get("name"),
            "descZh": zh.get("%s description" % pid) or "",
            "points": p.get("points"),
            "img": p.get("imageLink") or "",
        }

    perks = data.get("perks") or {}
    raw_name = zh.get("%s name" % data.get("id")) or ""
    # 上游中文表里这条只有英文原名（没有汉字）→ 当作英文名保留，不硬翻成中文
    name_en = raw_name if raw_name else ""
    name_zh = ""
    name_missing = False
    if raw_name and re.search(r"[\u4e00-\u9fff]", raw_name):
        name_zh = raw_name
    elif raw_name:
        name_missing = True
    return {
        "schema": 1,
        "id": data.get("id"),
        "nameEn": name_en,
        "nameZh": name_zh,
        "nameZhMissing": bool(name_missing),
        "start": data.get("start"),
        "end": data.get("end"),
        "startISO": time.strftime("%Y-%m-%d", time.localtime((data.get("start") or 0) / 1000.0))
        if data.get("start") else "",
        "endISO": time.strftime("%Y-%m-%d", time.localtime((data.get("end") or 0) / 1000.0))
        if data.get("end") else "",
        "perks": {
            "common": [perk(p) for p in (perks.get("common") or [])],
            "personal": [perk(p) for p in (perks.get("personal") or [])],
        },
        "source": "https://json.tarkov.dev/pvp-season/season（中文：season_zh）",
    }


def presence_index() -> dict:
    """任务 ID → 出现在哪些模式（直接读原始快照，先于标准化）。"""
    out = {}
    for mode in MODES:
        path = os.path.join(RAW_DIR, "tasks.%s.json" % mode)
        if not os.path.exists(path):
            continue
        for tid in (load_json(path)["data"]["tasks"] or {}):
            out.setdefault(tid, set()).add(mode)
    return out


VOLATILE_KEYS = ("generatedAt", "fetchedAt")


def canonical(payload) -> str:
    """校验用规范化 JSON：递归去掉时间戳，键排序，保证同输入同输出。"""
    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items() if k not in VOLATILE_KEYS}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return json.dumps(scrub(payload), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


class Verifier:
    """--verify 干跑：把重建结果与现有 data/tasks/*.json 比对，不写盘。"""

    def __init__(self):
        self.checked = 0
        self.failed = []

    def emit(self, path: str, payload) -> None:
        self.checked += 1
        name = os.path.basename(path)
        if not os.path.exists(path):
            self.failed.append(name)
            print("MISSING %s" % name)
            return
        rebuilt = canonical(payload)
        on_disk = canonical(load_json(path))
        digest = hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
        ok = rebuilt == on_disk
        print("%-24s %-5s sha256=%s" % (name, "MATCH" if ok else "DIFF", digest[:16]))
        if not ok:
            self.failed.append(name)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="只用 raw 快照重建")
    ap.add_argument("--verify", action="store_true",
                    help="干跑：重建并与现有 data/tasks/*.json 比对，不写盘")
    args = ap.parse_args(argv)

    verifier = Verifier() if args.verify else None
    write = verifier.emit if verifier else _write

    os.makedirs(TASKS_DIR, exist_ok=True)
    sources = fetch_raw(offline=args.offline)
    maps = map_index()
    items = item_index()
    known_en = known_english()
    curated_path = os.path.join(TASKS_DIR, "curated-guides.json")
    curated = load_json(curated_path) if os.path.exists(curated_path) else {}
    presence = presence_index()

    index = {"schema": 2, "tool": "tools/fetch_tasks.py",
             "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
             "build": "R19.23",
             "sourceLicense": "tarkov.dev 社区公开数据（非官方，CC/社区许可见 sources.json）",
             "modeOrder": list(MODES),
             "modes": {}, "modeMeta": {}, "mapsIndex": maps}
    all_traders = {}
    mode_ids = {}
    for mode in MODES:
        pack = build(mode, sources, maps, items, curated, known_en, presence)
        mode_ids[mode] = set(pack["tasks"])
        all_traders.update({k: v for k, v in pack["traders"].items()})
        objs = sum(len(t["objectives"]) for t in pack["tasks"].values())
        out_tasks = {
            "schema": 2, "mode": mode, "modeLabel": MODE_LABEL[mode],
            "upstreamGameMode": UPSTREAM[mode],
            "generatedAt": index["generatedAt"],
            "counts": {
                "tasks": len(pack["tasks"]),
                "objectives": objs,
                "withPrereq": sum(1 for t in pack["tasks"].values() if t["prerequisites"]),
                "edges": sum(len(t["prerequisites"]) for t in pack["tasks"].values()),
                "seasonOnly": sum(1 for t in pack["tasks"].values() if t["seasonOnly"]),
                "onlyHere": sum(1 for t in pack["tasks"].values()
                                if t["onlyInModes"] and t["onlyInModes"] == [mode]),
                "kappa": sum(1 for t in pack["tasks"].values() if t["kappaRequired"]),
                "faction": sum(1 for t in pack["tasks"].values() if t["faction"] != "Any"),
            },
            "tasks": pack["tasks"],
        }
        write(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), out_tasks)
        write(os.path.join(TASKS_DIR, "guides.%s.json" % mode),
               {"schema": 2, "mode": mode, "generatedAt": index["generatedAt"],
                "guides": pack["guides"]})
        index["modes"][mode] = {"label": MODE_LABEL[mode], "upstream": UPSTREAM[mode],
                               **out_tasks["counts"]}
        print("built %-8s tasks=%d edges=%d seasonOnly=%d" % (
            mode, out_tasks["counts"]["tasks"], out_tasks["counts"]["edges"],
            out_tasks["counts"]["seasonOnly"]))

    # 跨模式关系（严格按 ID 集合运算，不做名称合并）
    for mode in MODES:
        others = [m for m in MODES if m != mode]
        base = mode_ids[mode]
        meta = index["modeMeta"].setdefault(mode, {})
        meta["subsetOf"] = [m for m in others if base and base <= mode_ids[m]]
        meta["supersetOf"] = [m for m in others if mode_ids[m] and mode_ids[m] < base]
        meta["onlyHere"] = sorted(base - set().union(*[mode_ids[m] for m in others]))
        meta["missingVsOthers"] = {m: len(mode_ids[m] - base) for m in others}

    # 赛季元信息
    season = season_meta()
    if season:
        write(os.path.join(TASKS_DIR, "season.json"), season)
        index["season"] = {"id": season["id"], "nameEn": season["nameEn"],
                           "nameZh": season["nameZh"], "nameZhMissing": season["nameZhMissing"],
                           "startISO": season["startISO"], "endISO": season["endISO"],
                           "perks": len(season["perks"]["common"]) + len(season["perks"]["personal"])}
        print("season  %s  %s → %s  perks=%d" % (season["id"], season["startISO"],
                                                 season["endISO"], index["season"]["perks"]))

    # 商人表一致性（赛季端点也带 traders：完全相同就共用，不同则记录差异）
    trad_regular = load_json(os.path.join(RAW_DIR, "traders.regular.json"))["data"]
    trad_pvps_path = os.path.join(RAW_DIR, "traders.pvps.json")
    if os.path.exists(trad_pvps_path):
        trad_pvps = load_json(trad_pvps_path)["data"]
        same = (set(trad_regular) == set(trad_pvps) and all(
            (trad_regular[k].get("normalizedName"), trad_regular[k].get("imageLink")) ==
            (trad_pvps[k].get("normalizedName"), trad_pvps[k].get("imageLink"))
            for k in trad_regular))
        index["tradersIdentical"] = bool(same)
        if not same:
            index["tradersDiff"] = {
                "onlyRegular": sorted(set(trad_regular) - set(trad_pvps)),
                "onlyPvps": sorted(set(trad_pvps) - set(trad_regular)),
            }

    # R41 起 traders.json 带展示增强字段（游戏头像 / 中文名 tooltip）：
    # 这些不是上游任务端点能产出的，重跑时保留已有值，避免任务页头像丢失。
    traders_path = os.path.join(TASKS_DIR, "traders.json")
    if os.path.exists(traders_path):
        prev_traders = load_json(traders_path).get("traders") or {}
        for tid, rec in all_traders.items():
            prev = prev_traders.get(tid) or {}
            for key in ("portrait", "nameZh", "nameZhNote"):
                if prev.get(key):
                    rec[key] = prev[key]

    write(os.path.join(TASKS_DIR, "traders.json"),
           {"schema": 2, "generatedAt": index["generatedAt"], "traders": all_traders})
    write(os.path.join(TASKS_DIR, "sources.json"),
           {"schema": 2, "generatedAt": index["generatedAt"], "sources": sources,
            "failures": [{"mode": s["mode"], "endpoint": s["endpoint"], "error": s["error"]}
                         for s in sources if s.get("error")]})
    write(os.path.join(TASKS_DIR, "index.json"), index)
    if verifier:
        print("verify: %d files compared, %d mismatch" % (verifier.checked, len(verifier.failed)))
        if verifier.failed:
            print("DIFF: %s" % ", ".join(verifier.failed))
            return 1
        print("verify: reproducible（除生成时间戳外与现有数据完全一致）")
        return 0
    print("wrote data/tasks/{tasks.<mode>,guides.<mode>,traders,season,sources,index}.json")
    return 0


def _write(path: str, payload) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


if __name__ == "__main__":
    sys.exit(main())
