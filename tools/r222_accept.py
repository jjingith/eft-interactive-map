# -*- coding: utf-8 -*-
"""R222 真实浏览器验收：历史曲线必须画出采集器真正在落的那份快照。

修之前：界面永远显示「还没有历史快照 / 当前没有可用样本」，因为
`price_history.py` 只读 `data/flea-price-history/`（构建期才写），而采集器
写的是 `%LOCALAPPDATA%\\EFTPrice\\collect\\snapshots\\<模式>\\<日期>\\*.json.gz`。

本脚本只做实测，不认代码注释：
  1. PvP 模式下打开任一物品详情，「价格走势」必须出现真实折线（不是空态）；
  2. 折线样本数 ≥ 20，且与 `/api/price-history` 返回的 count 一致；
  3. 切到 24h 区间后样本数变少但仍有 ≥ 10 个点，且 ≤ 7 天区间的样本数；
  4. 截图留证。

用法：
    python tools/r222_accept.py --port 8787 --out D:/Temp/2/r222
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


def q(cdp, expr):
    return cdp.eval("Promise.resolve((function(){" + expr + "})())", await_promise=True)


def api_history(port, mode, item_id, days):
    url = ("http://127.0.0.1:%d/api/price-history?mode=%s&itemId=%s&days=%d"
           % (port, mode, item_id, days))
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


READ_HIST = r"""
  var host = document.querySelector('.mk-hist72');
  var foot = host ? host.querySelector('.mk-hist-foot') : null;
  var svg  = host ? host.querySelector('.mk-hist-svg') : null;
  var line = host ? host.querySelector('.mk-hist-line') : null;
  var empty = host ? host.querySelector('.mk-hist-empty') : null;
  return JSON.stringify({
    hasHost: !!host,
    hasSvg: !!svg,
    hasLine: !!line,
    lineLen: line ? (line.getAttribute('d') || '').length : 0,
    emptyText: empty ? (empty.textContent || '').trim() : '',
    foot: foot ? (foot.textContent || '').trim() : '',
    ranges: host ? Array.prototype.map.call(host.querySelectorAll('.mk-hist-range'),
              function (b) { return (b.textContent || '').trim(); }) : []
  });
"""


def read_hist(cdp):
    raw = q(cdp, READ_HIST)
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def samples_of(foot):
    m = re.search(r"样本：(\d+)\s*个快照", foot or "")
    return int(m.group(1)) if m else None


def click_range(cdp, label):
    expr = (r"""
      var host = document.querySelector('.mk-hist72');
      if (!host) { return false; }
      var btns = host.querySelectorAll('.mk-hist-range');
      for (var i = 0; i < btns.length; i++) {
        if ((btns[i].textContent || '').trim() === %s) { btns[i].click(); return true; }
      }
      return false;
    """ % json.dumps(label, ensure_ascii=False))
    return q(cdp, expr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9422)
    ap.add_argument("--out", default="D:/Temp/2/r222")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    checks = []
    shots = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)

        # 固定 PvP：模式是持久化的，残留 PvE 会让样本落到另一个目录
        q(cdp, "if (window.GWGameMode) { window.GWGameMode.set('regular', true); } return true;")
        q(cdp, "var b=document.getElementById('view-btn-market'); if(b){b.click();} return true;")
        base.wait_for(cdp, "(function(){var e=document.querySelector('.mk-cutoff');"
                          "return !!(e && (e.textContent||'').trim());})()", timeout=90, label="行情截止行")
        base.wait_for(cdp, "document.querySelectorAll('tr.mk-row').length > 0",
                      timeout=60, label="行情表格")

        item_id = q(cdp, "var tr=document.querySelector('tr.mk-row');"
                         "return tr ? tr.getAttribute('data-id') : '';")
        check("取到一行行情", bool(item_id), item_id)

        q(cdp, "var tr=document.querySelector('tr.mk-row');"
               "var n=tr?tr.querySelector('.mk-name'):null; if(n){n.click();} return true;")
        base.wait_for(cdp, "!!document.querySelector('.mk-hist72')", timeout=30, label="历史区块")
        base.wait_for(cdp,
                      "(function(){var h=document.querySelector('.mk-hist72');"
                      "if(!h){return false;}"
                      "if(h.querySelector('.mk-hist-svg')){return true;}"
                      "var e=h.querySelector('.mk-hist-empty');"
                      "var t=e?(e.textContent||''):'';"
                      "return !!e && t.indexOf('读取本机历史快照') < 0;})()",
                      timeout=90, label="历史曲线渲染完成")

        h7 = read_hist(cdp)
        shots.append(os.path.join(a.out, "r222-pvp-7d.png"))
        cdp.shot(shots[-1])

        check("7 天区间画出折线", h7.get("hasSvg") and h7.get("hasLine"), h7.get("emptyText"))
        n7 = samples_of(h7.get("foot"))
        check("7 天样本数 ≥ 20", (n7 or 0) >= 20, "样本=%s | %s" % (n7, h7.get("foot")))
        check("区间按钮齐全", h7.get("ranges") == ["24h", "7 天", "30 天", "全部"], h7.get("ranges"))

        api7 = api_history(a.port, "regular", item_id, 7)
        api_count = ((api7.get("series") or {}).get(item_id) or {}).get("count")
        check("样本数与接口一致", api_count == n7,
              "接口=%s 界面=%s | sources=%s" % (api_count, n7, api7.get("sources")))
        check("接口确实读到了采集器快照",
              (api7.get("sources") or {}).get("collector", 0) > 0,
              api7.get("sources"))

        # 切 24h
        check("点到 24h 区间", bool(click_range(cdp, "24h")), "24h")
        base.wait_for(cdp,
                      "(function(){var f=document.querySelector('.mk-hist-foot');"
                      "return !!(f && /样本：\\d+/.test(f.textContent||''));})()",
                      timeout=60, label="24h 曲线")
        time.sleep(0.6)
        h1 = read_hist(cdp)
        shots.append(os.path.join(a.out, "r222-pvp-24h.png"))
        cdp.shot(shots[-1])
        n1 = samples_of(h1.get("foot"))
        check("24h 区间画出折线", h1.get("hasSvg") and h1.get("hasLine"), h1.get("emptyText"))
        check("24h 样本数 ≥ 10", (n1 or 0) >= 10, "样本=%s | %s" % (n1, h1.get("foot")))
        check("24h 样本不多于 7 天", n1 is not None and n7 is not None and n1 <= n7,
              "24h=%s 7天=%s" % (n1, n7))

        api1 = api_history(a.port, "regular", item_id, 1)
        api1_count = ((api1.get("series") or {}).get(item_id) or {}).get("count")
        check("24h 样本数与接口一致", api1_count == n1, "接口=%s 界面=%s" % (api1_count, n1))

        report = {"item": item_id, "checks": checks, "shots": shots,
                  "page7": h7, "page1": h1,
                  "api7": {"used": api7.get("snapshotsUsed"),
                           "sources": api7.get("sources"),
                           "coverageDays": api7.get("coverageDays")},
                  "api1": {"used": api1.get("snapshotsUsed"),
                           "sources": api1.get("sources")}}
        path = os.path.join(a.out, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

        print("物品：%s" % item_id)
        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        print("7 天：样本 %s 个；接口 %s 份快照，来源 %s，覆盖 %s 天"
              % (n7, api7.get("snapshotsUsed"), api7.get("sources"), api7.get("coverageDays")))
        print("24h ：样本 %s 个；接口 %s 份快照" % (n1, api1.get("snapshotsUsed")))
        print("截图：%s" % ", ".join(os.path.basename(s) for s in shots))
        return 0 if all(c["ok"] for c in checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
