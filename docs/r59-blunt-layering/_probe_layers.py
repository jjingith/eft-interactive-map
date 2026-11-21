# -*- coding: utf-8 -*-
import json, urllib.request
PROXY = "http://127.0.0.1:7896"
op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"
URL = "https://api.tarkovgunsmith.com/GetSingleShotBallisticSimulation"


def post(layers, pen=42, dmg=80, adp=78):
    payload = {"penetration": pen, "damage": dmg, "armorDamagePerc": adp,
               "hitPoints": 80, "armorLayers": layers}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json",
        "Origin": "https://tarkovgunsmith.com", "Referer": "https://tarkovgunsmith.com/ballistic_calculator"})
    with op.open(req, timeout=40) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def L(is_plate, ac, bt, dur, maxd, mat=7):
    return {"isPlate": is_plate, "armorClass": ac, "bluntDamageThroughput": bt,
            "durability": dur, "maxDurability": maxd, "armorMaterial": mat}


cases = {
    "D_alone": [L(False, 5, 7.92, 50, 50)],          # Altyn 面罩 100%
    "E_alone": [L(False, 2, 9.9, 45, 45)],           # 类二级面罩 100%
    "D+E": [L(False, 5, 7.92, 50, 50), L(False, 2, 9.9, 45, 45)],
    "E+D": [L(False, 2, 9.9, 45, 45), L(False, 5, 7.92, 50, 50)],
    "P5+L2": [L(True, 5, 18, 50, 50), L(False, 2, 18, 40, 40)],
    "L2+P5": [L(False, 2, 18, 40, 40), L(True, 5, 18, 50, 50)],
}
for name, layers in cases.items():
    st, res = post(layers)
    print("==", name, st)
    for i, r in enumerate(res):
        print("  L%d penChance=%.6f penDmg=%.4f blunt=%.6f avgDmg=%.4f RF=%.6f postPen=%.6f"
              % (i + 1, r["PenetrationChance"], r["PenetrationDamage"], r["BluntDamage"],
                 r["AverageDamage"], r["ReductionFactor"], r["PostArmorPenetration"]))
