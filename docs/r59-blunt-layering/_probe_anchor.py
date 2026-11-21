# -*- coding: utf-8 -*-
import json, urllib.request
PROXY = "http://127.0.0.1:7896"
op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"
URL = "https://api.tarkovgunsmith.com/GetSingleShotBallisticSimulation"


def L(ac, bt, dur, maxd, plate=False):
    return {"isPlate": plate, "armorClass": ac, "bluntDamageThroughput": bt,
            "durability": dur, "maxDurability": maxd, "armorMaterial": 7}


def post(layers, pen, dmg, adp):
    req = urllib.request.Request(URL, data=json.dumps({
        "penetration": pen, "damage": dmg, "armorDamagePerc": adp,
        "hitPoints": 80, "armorLayers": layers}).encode("utf-8"), headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json",
        "Origin": "https://tarkovgunsmith.com", "Referer": "https://tarkovgunsmith.com/ballistic_calculator"})
    with op.open(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


for durpct in (100, 50, 10):
    a = post([L(5, 7.92, 50 * durpct / 100, 50)], 24, 96, 55)
    b = post([L(5, 7.92, 50 * durpct / 100, 50), L(2, 9.9, 45, 45)], 24, 96, 55)
    print("LOKT Altyn dur%d%% single=%.4f  pair L1=%.4f L2=%.4f RF1=%.4f D1=%.4f"
          % (durpct, a[0]["BluntDamage"], b[0]["BluntDamage"], b[1]["BluntDamage"],
             b[0]["ReductionFactor"], 96 * b[0]["ReductionFactor"]))
