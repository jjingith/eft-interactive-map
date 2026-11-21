# -*- coding: utf-8 -*-
"""R59: 用 tarkovgunsmith 单发弹道接口实测「第二层护甲钝伤」规则。

只读外部 API，不改业务代码。代理 127.0.0.1:7896。
所有原始响应写入 evidence.json，便于离线复算。
"""
import json
import os
import time
import urllib.error
import urllib.request

PROXY = "http://127.0.0.1:7896"
URL = "https://api.tarkovgunsmith.com/GetSingleShotBallisticSimulation"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
EVIDENCE = os.path.join(OUT_DIR, "r59-blunt-layering-evidence.json")

_op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def post(layers, pen, dmg, adp):
    payload = {"penetration": pen, "damage": dmg, "armorDamagePerc": adp,
               "hitPoints": 80, "armorLayers": layers}
    body = json.dumps(payload).encode("utf-8")
    last = None
    for attempt in range(4):
        req = urllib.request.Request(URL, data=body, headers={
            "User-Agent": UA, "Content-Type": "application/json",
            "Accept": "application/json", "Origin": "https://tarkovgunsmith.com",
            "Referer": "https://tarkovgunsmith.com/ballistic_calculator"})
        try:
            with _op.open(req, timeout=45) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError("POST failed: %s" % last)


def layer(item, dur_pct, mat=7):
    item = LAYERS[item]
    dur = item["max"] * dur_pct / 100.0
    return {"isPlate": item["isPlate"], "armorClass": item["ac"],
            "bluntDamageThroughput": item["bt"], "durability": dur,
            "maxDurability": item["max"], "armorMaterial": mat}


LAYERS = {
    "ALTYN5":   {"isPlate": False, "ac": 5, "bt": 7.92,  "max": 50},   # Altyn 面罩
    "MASK2":    {"isPlate": False, "ac": 2, "bt": 9.9,   "max": 45},   # 二级面罩
    "SOFT2":    {"isPlate": False, "ac": 2, "bt": 18.0,  "max": 40},   # 软内衬
    "SOFT4":    {"isPlate": False, "ac": 4, "bt": 15.48, "max": 180},  # 四级软层
    "PLATE5":   {"isPlate": True,  "ac": 5, "bt": 18.0,  "max": 50},   # 五级插板
    "PLATE6":   {"isPlate": True,  "ac": 6, "bt": 20.0,  "max": 60},   # 六级插板
}
AMMOS = {
    "ME308": {"pen": 42.0, "dmg": 80.0, "adp": 78},   # .308 ME
    "LOWPEN": {"pen": 15.0, "dmg": 60.0, "adp": 20},
    "HIGHPEN": {"pen": 70.0, "dmg": 35.0, "adp": 30},
}


def factor_a(ac, dur_pct):
    return (121 - 5000 / (45 + dur_pct * 2)) * ac * 0.1


def blunt_scale(ac, dur_pct, pen):
    return min(1.0, max(0.2, 1 - 0.03 * (factor_a(ac, dur_pct) - pen)))


def blunt_single(ac, dur_pct, bt_pct, dmg, pen):
    return (bt_pct / 100.0) * blunt_scale(ac, dur_pct, pen) * dmg


def reduction(ac, dur_pct, pen):
    return min(1.0, max(0.6, pen / (factor_a(ac, dur_pct) + 12.0)))


singles = {}   # (item,dur_pct,ammo) -> result


def single(item, dur_pct, ammo):
    key = (item, dur_pct, ammo)
    if key not in singles:
        a = AMMOS[ammo]
        st, res = post([layer(item, dur_pct)], a["pen"], a["dmg"], a["adp"])
        singles[key] = {"status": st, "out": res[0]}
        time.sleep(0.05)
    return singles[key]["out"]


PAIRS = [
    # name, layer1, layer2, (dur1,dur2) list, ammo list
    ("ALTYN5+MASK2", "ALTYN5", "MASK2", [(100, 100), (50, 100), (10, 100), (100, 50), (100, 10)], ["ME308", "LOWPEN", "HIGHPEN"]),
    ("MASK2+ALTYN5", "MASK2", "ALTYN5", [(100, 100), (50, 100), (10, 100), (100, 50), (100, 10)], ["ME308"]),
    ("PLATE5+SOFT2", "PLATE5", "SOFT2", [(100, 100), (50, 100), (10, 100), (100, 50), (100, 10)], ["ME308", "LOWPEN", "HIGHPEN"]),
    ("SOFT2+PLATE5", "SOFT2", "PLATE5", [(100, 100), (50, 100), (10, 100), (100, 50), (100, 10)], ["ME308"]),
    ("PLATE6+SOFT4", "PLATE6", "SOFT4", [(100, 100), (50, 100), (10, 100), (100, 50), (100, 10)], ["ME308"]),
    ("PLATE5+MASK2", "PLATE5", "MASK2", [(100, 100), (100, 10)], ["ME308"]),
]

raw = []
fitting = []
k_pairs = []
triple = None
anchor = None


def evaluate(name, it1, it2, d1, d2, ammo):
    a = AMMOS[ammo]
    L1 = layer(it1, d1)
    L2 = layer(it2, d2)
    st, res = post([L1, L2], a["pen"], a["dmg"], a["adp"])
    o1, o2 = res[0], res[1]
    s1 = single(it1, d1, ammo)          # 第一层单独（同样耐久/弹药）
    s2 = single(it2, d2, ammo)          # 第二层单独
    bt1 = LAYERS[it1]["bt"] / 100.0
    bt2 = LAYERS[it2]["bt"] / 100.0
    plate_mul2 = 0.6 if (LAYERS[it2]["isPlate"] and any(not LAYERS[x]["isPlate"] for x in (it1, it2))) else 1.0
    bt2_eff = bt2 * plate_mul2
    bt1_eff = bt1 * (0.6 if (LAYERS[it1]["isPlate"] and any(not LAYERS[x]["isPlate"] for x in (it1, it2))) else 1.0)
    RF1 = o1["ReductionFactor"]
    P1 = a["pen"] * RF1
    D1 = a["dmg"] * RF1
    obs = o2["BluntDamage"]
    b1_obs = o1["BluntDamage"]

    # 第四假设 H4：第二层用「穿透路径」衰减后的 P/D 重算完整公式
    h4 = bt2_eff * blunt_scale(LAYERS[it2]["ac"], d2, P1) * D1
    # H1：现有 bluntCarry —— 上一层钝伤 × 本层 BT × 本层 scale(原始 P,D)
    h1 = b1_obs * bt2_eff * blunt_scale(LAYERS[it2]["ac"], d2, a["pen"])
    # H3：上一层钝伤 × 本层 BT（不重算 FactorA）
    h3 = b1_obs * bt2_eff
    # 单层基准（第二层单独输出，用于对照其原始语义）
    b2_alone = s2["BluntDamage"]
    b1_alone = s1["BluntDamage"]

    rec = {
        "case": name, "layer1": it1, "layer2": it2, "dur1_pct": d1, "dur2_pct": d2,
        "ammo": ammo, "pen": a["pen"], "dmg": a["dmg"],
        "site_layer1": o1, "site_layer2": o2,
        "single_layer1_blunt": b1_alone, "single_layer2_blunt": b2_alone,
        "bt1_eff": bt1_eff, "bt2_eff": bt2_eff,
        "RF1": RF1, "P1": P1, "D1": D1,
        "obs_B2": obs,
        "H1": h1, "H3": h3, "H4": h4,
        "err_H1": h1 - obs, "err_H3": h3 - obs, "err_H4": h4 - obs,
        "pct_H1": (h1 - obs) / obs * 100 if obs else None,
        "pct_H3": (h3 - obs) / obs * 100 if obs else None,
        "pct_H4": (h4 - obs) / obs * 100 if obs else None,
        "ratio_obs_over_B1": obs / b1_obs if b1_obs else None,
    }
    # H2：每对固定系数 k，最小二乘 k = sum(B1*obs)/sum(B1^2)
    raw.append(rec)
    return rec


def fit_k(records):
    num = sum(r["site_layer1"]["BluntDamage"] * r["obs_B2"] for r in records)
    den = sum(r["site_layer1"]["BluntDamage"] ** 2 for r in records)
    return num / den if den else None


# ---------- 采样 ----------
for (name, it1, it2, combos, ammos) in PAIRS:
    for ammo in ammos:
        for (d1, d2) in combos:
            evaluate(name, it1, it2, d1, d2, ammo)

# 三层链路（头链），主弹药
a = AMMOS["ME308"]
st, res = post([layer("ALTYN5", 100), layer("MASK2", 100), layer("MASK2", 100)],
               a["pen"], a["dmg"], a["adp"])
triple = {"site": res,
          "H1_chain": None, "H4_chain": None}
b1 = res[0]["BluntDamage"]
rf = 1.0
P = a["pen"]
D = a["dmg"]
chain_h1 = b1
chain_h4 = None
for idx, it in enumerate(["ALTYN5", "MASK2", "MASK2"]):
    L = LAYERS[it]
    if idx == 0:
        b1c = res[0]["BluntDamage"]
        chain_h1 = b1c
        chain_h4 = res[0]["BluntDamage"]
        P = a["pen"] * res[0]["ReductionFactor"]
        D = a["dmg"] * res[0]["ReductionFactor"]
        continue
    bt = L["bt"] / 100.0
    chain_h1 = chain_h1 * bt * blunt_scale(L["ac"], 100, a["pen"])
    chain_h4 = bt * blunt_scale(L["ac"], 100, P) * D
    P = P * res[idx]["ReductionFactor"]
    D = D * res[idx]["ReductionFactor"]
triple["H1_chain"] = chain_h1
triple["H4_chain"] = chain_h4

# 锚点还原：视频前提「第一层 8 点」→ 反推 D=100,P=60,BT1=8%,class5,scale=1；
# 第二层按二级面罩 BT=9.9%（真实 Tac-Kek）与 12.5%（拟合到 1 点）各算一次
anchor_inputs = {"pen": 60.0, "dmg": 100.0, "adp": 50}
st, res = post([layer("ALTYN5", 100), layer("MASK2", 100)],
               anchor_inputs["pen"], anchor_inputs["dmg"], anchor_inputs["adp"])
# 把 class5 BT 改成 8.0 才能得到 8 点（Altyn 是 7.92 → 7.92 点）
anchor = {
    "inputs": anchor_inputs,
    "site_bt792": res,
    "note": "Altyn 面罩 BT=7.92% 时第一层钝伤≈7.92；视频口述取整为 8。",
}
# 用 BT=8.0 / 第二层 BT=9.9 的解析值（与站点同口径）
D = anchor_inputs["dmg"]
P = anchor_inputs["pen"]
RF1 = reduction(5, 100, P)
D1 = D * RF1
P1 = P * RF1
B1 = 0.08 * blunt_scale(5, 100, P) * D
B2 = 0.099 * blunt_scale(2, 100, P) * D1
H1a = B1 * 0.099 * blunt_scale(2, 100, P)
H3a = B1 * 0.099
H4a = B2
anchor["analytic_bt8_mask99"] = {
    "B1": B1, "RF1": RF1, "H1": H1a, "H2_k_eq_BT2": B1 * 0.099,
    "H3": H3a, "H4": H4a,
    "mask125_H1": B1 * 0.125 * 1.0, "mask125_H4": 0.125 * 1.0 * D1,
}

# H2 按 pair 拟合
by_pair = {}
for r in raw:
    by_pair.setdefault((r["case"], r["layer1"], r["layer2"]), []).append(r)
for key, recs in by_pair.items():
    k = fit_k(recs)
    for r in recs:
        r["H2_k"] = k
        r["H2"] = r["site_layer1"]["BluntDamage"] * k
        r["err_H2"] = r["H2"] - r["obs_B2"]
        r["pct_H2"] = (r["H2"] - r["obs_B2"]) / r["obs_B2"] * 100 if r["obs_B2"] else None
    k_pairs.append({"case": key[0], "k": k, "n": len(recs)})

k_global = fit_k(raw)
for r in raw:
    r["H2_global"] = r["site_layer1"]["BluntDamage"] * k_global
    r["err_H2_global"] = r["H2_global"] - r["obs_B2"]
    r["pct_H2_global"] = (r["H2_global"] - r["obs_B2"]) / r["obs_B2"] * 100 if r["obs_B2"] else None


def agg(field_pred, field_err, field_pct):
    abs_err = [abs(r[field_err]) for r in raw]
    pct = [abs(r[field_pct]) for r in raw if r[field_pct] is not None]
    return {
        "n": len(raw),
        "max_abs": max(abs_err) if abs_err else None,
        "mean_abs": (sum(abs_err) / len(abs_err)) if abs_err else None,
        "max_pct": max(pct) if pct else None,
        "mean_pct": (sum(pct) / len(pct)) if pct else None,
        "within_001": sum(1 for x in abs_err if x <= 0.01),
    }


summary = {
    "H1": agg("H1", "err_H1", "pct_H1"),
    "H2_pair": agg("H2", "err_H2", "pct_H2"),
    "H2_global": agg("H2_global", "err_H2_global", "pct_H2_global"),
    "H3": agg("H3", "err_H3", "pct_H3"),
    "H4": agg("H4", "err_H4", "pct_H4"),
}
summary["k_global"] = k_global

evidence = {
    "round": "R59",
    "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "endpoint": URL,
    "proxy": PROXY,
    "note": "每个组合先按同一弹药/耐久单独请求两层，再请求两层组合；H2 的 k 用最小二乘按组合拟合。",
    "layerDefs": LAYERS,
    "ammoDefs": AMMOS,
    "samples": raw,
    "singles": {("%s|%d|%s" % k): v["out"] for k, v in singles.items()},
    "triple": triple,
    "anchor": anchor,
    "kPairs": k_pairs,
    "summary": summary,
    "statusAll": sorted({r["site_layer1"].get("_status", 200) for r in raw}),
}
os.makedirs(OUT_DIR, exist_ok=True)
with open(EVIDENCE, "w", encoding="utf-8") as f:
    json.dump(evidence, f, ensure_ascii=False, indent=1)

print("samples:", len(raw))
print("k_pairs:", [(x["case"], round(x["k"], 5)) for x in k_pairs])
print("k_global:", k_global)
for k, v in summary.items():
    if k == "k_global":
        continue
    print(k, "max_abs=%.3g mean_abs=%.3g max_pct=%.3g mean_pct=%.3g within0.01=%d/%d"
          % (v["max_abs"], v["mean_abs"], v["max_pct"], v["mean_pct"], v["within_001"], v["n"]))
print("triple site blunt:", [round(x["BluntDamage"], 4) for x in triple["site"]],
      "H1chain=%.4f H4chain=%.4f" % (triple["H1_chain"], triple["H4_chain"]))
print("anchor site:", [(round(x["BluntDamage"], 4), round(x["ReductionFactor"], 4)) for x in anchor["site_bt792"]])
print("anal anchor:", {k: round(v, 4) for k, v in anchor["analytic_bt8_mask99"].items()})
print("evidence ->", EVIDENCE)
