# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error

PROXY = "http://127.0.0.1:7896"
op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

payload = {
    "penetration": 28, "damage": 56, "armorDamagePerc": 25, "hitPoints": 80,
    "armorLayers": [
        {"isPlate": False, "armorClass": 4, "bluntDamageThroughput": 26,
         "durability": 40, "maxDurability": 40, "armorMaterial": 7}
    ],
}
body = json.dumps(payload).encode("utf-8")
for base in ["https://api.tarkovgunsmith.com", "https://tarkovgunsmith.com/api",
             "https://api.tarkovgunsmith.com/api"]:
    url = base + "/GetSingleShotBallisticSimulation"
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json",
        "Origin": "https://tarkovgunsmith.com", "Referer": "https://tarkovgunsmith.com/ballistic_calculator"})
    try:
        with op.open(req, timeout=40) as r:
            raw = r.read()
            print("OK", url, r.status, raw[:400])
    except urllib.error.HTTPError as e:
        print("HTTPERR", url, e.code, e.read()[:200])
    except Exception as e:
        print("ERR", url, type(e).__name__, str(e)[:200])
