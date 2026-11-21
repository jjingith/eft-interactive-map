# -*- coding: utf-8 -*-
"""R54b：用上游权威字段补 5 件缺失护甲的钝伤系数（BT），并交叉校验 R54 反解结果。

数据源优先级
    1. tarkov.dev GraphQL  https://api.tarkov.dev/graphql （POST items(ids:[...])）
    2. tarkov.dev 静态导出 https://json.tarkov.dev/regular/items （GraphQL 同一份数据的公开镜像）
    3. 项目内离线快照 build-cache/tarkovdev/regular/items.json（json.tarkov.dev 构建期抓取）
    4. 项目蒸馏快照 data/items.json（同源，aps 已带 bt，可做第二重校验）

字段口径（关键）
    上游 armor 的根 properties.bluntThroughput 恒为 0，**不是**可用值；
    真正的逐部位钝伤系数在 properties.armorSlots[].bluntThroughput
    （头盔为 Helmet_top/Helmet_back/helmet_eyes…，软甲为 Soft_armor_front/back/left/right）。
    gunsmith 的 per-item BT 与 tarkov.dev armorSlots 的 BT 在 THOR 三件上完全同值，
    说明两者是同一物理量（穿透后的钝伤比例），可直接交叉校验。

用法（项目根目录）
    python tools/r54b_upstream_bt.py                 # 联网优先，失败回落快照，并写库
    python tools/r54b_upstream_bt.py --offline       # 只用本地快照，不联网
    python tools/r54b_upstream_bt.py --no-write      # 只算校验，不改 data/armor-bt.json

只依赖 Python 标准库；外网经 127.0.0.1:7896 代理（可用 R54_PROXY 覆盖），本地地址直连。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(ROOT, "data", "armor-bt.json")
LOCAL_ITEMS = os.path.join(ROOT, "data", "items.json")
SNAPSHOT = os.path.join(ROOT, "build-cache", "tarkovdev", "regular", "items.json")
EVIDENCE_JSON = os.path.join(ROOT, "docs", "r54b-upstream-bt-evidence.json")

PROXY = os.environ.get("R54_PROXY", "http://127.0.0.1:7896")
TARGETS = [
    "69cbfe44897389c1870b2337",
    "6a567ae55cbe811cbe0136a8",
    "6a568dda1d89fcfb35010389",
    "6a576f2105af50743903b74c",
    "6a670ae11ab6ac490a0b9a99",
]
CROSSCHECK = [
    "5fd4c474dd870108a754b241",
    "609e8540d5c319764c2bc2e9",
    "60a283193cb70855c43a381d",
    "68a89146212dbbeead0d5636",
]
ALL_IDS = TARGETS + CROSSCHECK
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
EXPORT_URL = "https://json.tarkov.dev/regular/items"
GRAPHQL_URL = "https://api.tarkov.dev/graphql"


def log(msg):
    print(msg, flush=True)


def proxy_alive():
    try:
        socket.create_connection(("127.0.0.1", 7896), timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


def opener():
    hosts = {"http": PROXY, "https": PROXY}
    return urllib.request.build_opener(urllib.request.ProxyHandler(hosts))


def fetch_export():
    """抓 json.tarkov.dev 静态导出（GraphQL 同源公开镜像）。"""
    req = urllib.request.Request(EXPORT_URL, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9"})
    last = None
    for i in range(3):
        try:
            with opener().open(req, timeout=180) as r:
                if r.status != 200:
                    raise RuntimeError("HTTP %s" % r.status)
                body = r.read()
                return {
                    "endpoint": EXPORT_URL,
                    "status": r.status,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "data": json.loads(body.decode("utf-8")),
                }
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (i + 1))
    raise RuntimeError("GET %s 失败: %s" % (EXPORT_URL, last))


def query_graphql(ids):
    """尝试 GraphQL；上游不可用时返回错误记录（不阻塞后续静态导出）。"""
    q = (
        'query { items(ids: [%s]) { id name properties { __typename '
        '... on ItemPropertiesArmor { bluntThroughput armorSlots { nameId bluntThroughput class durability armorMaterial } } '
        '... on ItemPropertiesHelmet { bluntThroughput armorSlots { nameId bluntThroughput class durability armorMaterial } } '
        '... on ItemPropertiesChestRig { bluntThroughput armorSlots { nameId bluntThroughput class durability armorMaterial } } '
        '} } }' % ", ".join('"%s"' % i for i in ids)
    )
    req = urllib.request.Request(GRAPHQL_URL, data=json.dumps({"query": q}).encode("utf-8"),
                                 headers={"User-Agent": UA, "Content-Type": "application/json",
                                          "Accept": "application/json",
                                          "Origin": "https://tarkov.dev",
                                          "Referer": "https://tarkov.dev/"})
    try:
        with opener().open(req, timeout=60) as r:
            body = json.loads(r.read().decode("utf-8"))
            return {"endpoint": GRAPHQL_URL, "status": r.status, "ok": "errors" not in body,
                    "errors": body.get("errors"), "data": body.get("data")}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return {"endpoint": GRAPHQL_URL, "status": e.code, "ok": False, "errors": [raw[:300]]}
    except Exception as e:  # noqa: BLE001
        return {"endpoint": GRAPHQL_URL, "status": None, "ok": False, "errors": [str(e)[:300]]}


def load_snapshot():
    with open(SNAPSHOT, "rb") as f:
        raw = f.read()
    return {
        "endpoint": SNAPSHOT,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(os.path.getmtime(SNAPSHOT))),
        "data": json.loads(raw.decode("utf-8")),
    }


def items_of(payload):
    """兼容 {'data': {'items': {...}}} 与 {'items': {...}}。"""
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    return payload


def slot_rows(props):
    rows = []
    for s in (props.get("armorSlots") or []):
        if "bluntThroughput" not in s:
            continue
        rows.append({
            "nameId": s.get("nameId"),
            "bluntThroughput": s.get("bluntThroughput"),
            "class": s.get("class"),
            "durability": s.get("durability"),
            "armorMaterial": s.get("armorMaterial"),
            "zones": s.get("zones"),
        })
    return rows


def effective_bt(rows):
    """取 armorSlots 中一致的那一个值；无软甲槽（纯插板挂载）返回 None。"""
    vals = [r["bluntThroughput"] for r in rows if r["bluntThroughput"] is not None]
    if not vals:
        return None
    uniq = sorted(set(round(v, 6) for v in vals))
    if len(uniq) > 1:
        raise RuntimeError("armorSlots BT 不一致: %s" % uniq)
    return uniq[0]


_LOCAL_CACHE = {}


def local_bt(iid):
    if not _LOCAL_CACHE:
        with open(LOCAL_ITEMS, encoding="utf-8") as f:
            _LOCAL_CACHE.update(json.load(f)["items"])
    ent = _LOCAL_CACHE.get(iid) or {}
    aps = ent.get("aps") or []
    vals = [a.get("bt") for a in aps if a.get("bt") is not None]
    return {
        "found": bool(ent),
        "rootBt": ent.get("bt"),
        "rootClass": ent.get("cl"),
        "rootDurability": ent.get("dur"),
        "rootMaterial": ent.get("mat"),
        "slotBts": sorted(set(vals)),
        "slotRows": [{"zone": a.get("zone"), "bt": a.get("bt"), "class": a.get("cl"),
                      "durability": a.get("dur"), "material": a.get("mat")}
                     for a in aps if a.get("bt") is not None],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="只用本地快照，不联网")
    ap.add_argument("--no-write", action="store_true", help="只算校验，不写 data/armor-bt.json")
    args = ap.parse_args()

    with open(DATA_JSON, encoding="utf-8") as f:
        db = json.load(f)

    log("proxy 127.0.0.1:7896: %s" % ("reachable" if proxy_alive() else "unreachable"))

    gql = None
    if not args.offline:
        gql = query_graphql(ALL_IDS)
        log("graphql %s -> %s" % (GRAPHQL_URL, gql.get("status")))
        if not gql.get("ok"):
            log("  graphql errors: %s" % json.dumps(gql.get("errors"), ensure_ascii=False)[:200])

    src = None
    if not args.offline:
        try:
            raw = fetch_export()
            src = {"kind": "json.tarkov.dev", **{k: v for k, v in raw.items() if k != "data"}}
            upstream = items_of(raw["data"])
            log("live export %s bytes sha256=%s" % (raw["bytes"], raw["sha256"][:16]))
        except Exception as e:  # noqa: BLE001
            log("live export 失败，回落本地快照：%s" % e)
    if src is None:
        raw = load_snapshot()
        src = {"kind": "local-snapshot", **{k: v for k, v in raw.items() if k != "data"}}
        upstream = items_of(raw["data"])
        log("offline snapshot %s bytes sha256=%s" % (raw["bytes"], raw["sha256"][:16]))

    # 若 GraphQL 真的可用，用它覆盖同 id 的结果并记录来源
    gql_items = {}
    if gql and gql.get("ok") and gql.get("data", {}).get("items"):
        for it in gql["data"]["items"]:
            props = it.get("properties") or {}
            gql_items[it["id"]] = {"properties": props, "name": it.get("name")}

    evidence = {
        "round": "R54b",
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "proxy": PROXY,
        "field": "properties.armorSlots[].bluntThroughput",
        "graphql": {k: v for k, v in (gql or {}).items() if k != "data"},
        "source": src,
        "targets": {},
        "crossCheck": {},
        "notes": {
            "rootField": "properties.bluntThroughput 在 armor 条目上恒为 0，不可直接当 BT 使用",
            "slotField": "逐部位 BT 在 armorSlots[]；头盔各槽同值，软甲软层同值，纯插板槽无此字段",
        },
    }

    for iid in ALL_IDS:
        item = upstream.get(iid)
        gitem = gql_items.get(iid)
        if item is None and gitem is None:
            log("MISSING upstream %s" % iid)
            evidence["targets" if iid in TARGETS else "crossCheck"][iid] = {"found": False}
            continue
        if gitem is not None:
            props = gitem.get("properties") or {}
            norm = gitem.get("name")
            srcName = "graphql"
        else:
            props = item.get("properties") or {}
            norm = item.get("normalizedName")
            srcName = src["kind"]
        rows = slot_rows(props)
        bt = effective_bt(rows) if rows else None
        rec = {
            "found": True,
            "source": srcName,
            "normalizedName": norm,
            "rootBluntThroughput": props.get("bluntThroughput"),
            "rootClass": props.get("class"),
            "rootDurability": props.get("durability"),
            "rootMaterial": props.get("material"),
            "propertiesType": props.get("propertiesType"),
            "armorSlots": rows,
            "effectiveBt": bt,
            "localItemsJson": local_bt(iid),
        }
        if iid in TARGETS:
            evidence["targets"][iid] = rec
            log("%s bt=%s slots=%d name=%s" % (iid, bt, len(rows), norm))
        else:
            entry = db["items"].get(iid) or {}
            rec["publishedInDb"] = entry.get("bt")
            rec["dbSource"] = entry.get("btSource")
            if bt is None:
                rec["verdict"] = "no-upstream-slot-bt"
                rec["delta"] = None
            else:
                rec["delta"] = round(entry.get("bt", 0) - bt, 8)
                rec["verdict"] = "match" if abs(rec["delta"]) < 0.01 else "mismatch"
            evidence["crossCheck"][iid] = rec
            log("%s crosscheck db=%s upstream=%s delta=%s %s"
                % (iid, entry.get("bt"), bt, rec["delta"], rec["verdict"]))

    # 写库：仅 5 个目标；保留 btFallback 作为兜底记录
    changed = []
    for iid in TARGETS:
        rec = evidence["targets"].get(iid) or {}
        bt = rec.get("effectiveBt")
        if bt is None:
            continue
        ent = db["items"][iid]
        old = ent.get("bt")
        ent["bt"] = round(bt, 4)
        ent["btSource"] = "tarkov.dev:armorSlots.bluntThroughput"
        ent["btFallback"] = old
        ent["btFallbackSource"] = "material-fallback"
        ent["btEvidence"] = {
            "source": rec["source"],
            "field": "properties.armorSlots[].bluntThroughput",
            "endpoint": src.get("endpoint"),
            "fetchedAt": src.get("checkedAt") or src.get("mtime"),
            "sha256": src.get("sha256"),
            "rootBluntThroughput": rec.get("rootBluntThroughput"),
            "armorClass": rec.get("rootClass"),
            "durability": rec.get("rootDurability"),
            "material": rec.get("rootMaterial"),
            "slots": rec.get("armorSlots"),
            "inverted": ent["bt"],
        }
        changed.append((iid, old, ent["bt"], rec["source"]))

    db.setdefault("source", {})["upstream"] = {
        "round": "R54b",
        "field": "properties.armorSlots[].bluntThroughput",
        "endpoint": src.get("endpoint"),
        "kind": src.get("kind"),
        "bytes": src.get("bytes"),
        "sha256": src.get("sha256"),
        "fetchedAt": src.get("checkedAt") or src.get("mtime"),
        "note": "根 properties.bluntThroughput 恒为 0；逐部位值取 armorSlots[]。"
                "5 件原 material-fallback 已改由上游字段覆盖，兜底值保留在 btFallback。",
        "graphql": {k: v for k, v in (gql or {}).items() if k != "data"},
    }

    planned = [
        {"id": i, "from": old, "to": new, "source": s} for i, old, new, s in changed
    ]
    evidence["planned"] = planned

    os.makedirs(os.path.dirname(EVIDENCE_JSON), exist_ok=True)

    if args.no_write:
        log("--no-write：未写 data/armor-bt.json；即将写入的变更：")
        for row in changed:
            log("  %s %s -> %s (%s)" % row)
    else:
        evidence["written"] = planned
        with open(DATA_JSON, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=1)
            f.write("\n")
        log("已写 %s；变更 %d 条" % (DATA_JSON, len(changed)))

    with open(EVIDENCE_JSON, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=1)
    log("evidence -> %s" % EVIDENCE_JSON)


if __name__ == "__main__":
    main()
