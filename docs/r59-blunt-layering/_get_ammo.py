# -*- coding: utf-8 -*-
import json, urllib.request
PROXY = "http://127.0.0.1:7896"
op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"
req = urllib.request.Request("https://api.tarkovgunsmith.com/GetAmmoDataSheetData",
                             headers={"User-Agent": UA, "Accept": "application/json"})
with op.open(req, timeout=60) as r:
    d = json.loads(r.read().decode("utf-8"))
print(type(d), (list(d)[:10] if isinstance(d, dict) else len(d)))
s = json.dumps(d, ensure_ascii=False)
print(s[:800])
open(r"d:\personal\trae\02-塔科夫\eft-interactive-map\docs\r59-blunt-layering\_ammo_raw.json", "w", encoding="utf-8").write(s)
