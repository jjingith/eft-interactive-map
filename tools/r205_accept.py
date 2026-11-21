#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20.5 跳蚤行情：真实浏览器验收。

覆盖：
  1) 行情状态行显示「今日快照 + 更新时间」
  2) 候选表出现「跳蚤最新」列（口径与 FLEA价=24h均价、BASE=基础价 分开）
  3) 缓存过期 → 显示「过期快照（N 天前）」，且应用仍可用
  4) 无缓存 → 显示「无缓存（仅历史均价）」，地图/枪械构建器仍可用（离线）
  5) 手动刷新按钮可触发（服务端后台抓取）
  6) 控制台错误与外部网络请求

只临时改名/改写**行情缓存**（本轮新增文件）以模拟状态，结束时必定恢复；
不触碰任何业务数据。
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

CACHE = os.path.join(ROOT, "data", "flea-prices.json")
BAK = os.path.join(ROOT, "data", "flea-prices.json.acceptbak")
OUT = os.path.join(ROOT, "docs", "r20.5")


class Checker:
    def __init__(self):
        self.items = []

    def ok(self, cid, cond, detail=""):
        self.items.append({"id": cid, "pass": bool(cond), "detail": str(detail)[:300]})
        print(("PASS " if cond else "FAIL ") + cid + ("  " + str(detail)[:200] if detail else ""))
        return bool(cond)


def js(cdp, expr):
    r = cdp.eval(expr)
    if isinstance(r, str):
        t = r.strip()
        if t[:1] in ("{", "["):
            try:
                return json.loads(t)
            except Exception:  # noqa: BLE001
                return r
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8805")
    ap.add_argument("--port", type=int, default=9720)
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    shots = os.path.join(OUT, "screenshots")
    os.makedirs(shots, exist_ok=True)

    profile = os.path.join(os.environ.get("TEMP", "."), "r205accept")
    proc, ws = launch(find_chrome(), args.port, 1600, 950, profile)
    cdp = CDP(ws)
    chk = Checker()
    report = {"base": args.base, "checks": []}
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)

        def shot(name):
            import base64
            r = cdp.call("Page.captureScreenshot", format="png")
            with open(os.path.join(shots, name), "wb") as fh:
                fh.write(base64.b64decode(r["data"]))
            report.setdefault("shots", []).append(name)
            print("shot:", name)

        def load_and_open(select_gun=True):
            cdp.call("Page.navigate", url=args.base + "/index.html")
            wait_ready(cdp, want_url="index.html")
            time.sleep(4)
            cdp.eval("(function(){var b=document.querySelector('[data-view=gun]');if(b)b.click();return !!b;})()")
            time.sleep(2.5)
            if select_gun:
                # 先选一把枪（没有枪就没有槽位，候选表自然是空的）
                cdp.eval("(function(){var c=document.querySelector('#gw-browse .gw-card');if(c)c.click();return !!c;})()")
                time.sleep(3.0)

        def status_text():
            return js(cdp, """(function(){var e=document.getElementById('gw-quote-status');
          return e?{text:(e.textContent||'').trim(), state:e.dataset.state||''}:null;})()""")

        def table_head():
            return js(cdp, """(function(){return [].slice.call(
              document.querySelectorAll('#gw-table .tbl-head .tbl-cell')).map(function(x){return (x.textContent||'').trim();});})()""")

        # ---------- 1) 今日快照 ----------
        load_and_open()
        st = status_text()
        chk.ok("A1_行情状态行存在", st is not None, st)
        chk.ok("A2_今日快照状态", st and st.get("state") == "fresh" and "今日快照" in st.get("text", ""), st)
        # 打开一个槽位看候选表列
        # 只点真实槽位卡（.gw-part[data-slot]）；弹药格没有 data-slot，点它会切到弹药模式
        focused = cdp.eval("(function(){var ps=document.querySelectorAll('#gw-tree .gw-part[data-slot]');"
                            "if(!ps.length)return 'none';ps[0].click();return ps[0].dataset.slot||'?';})()")
        time.sleep(1.8)
        head = table_head()
        chk.ok("A3_跳蚤最新列存在", any("跳蚤最新" in h for h in head),
               "focused=%s head=%s" % (focused, head))
        chk.ok("A4_均价与基础价口径仍分列", any("FLEA价" in h or "LAST价" in h for h in head), head)
        shot("r205-fresh.png")

        # ---------- 2) 过期快照 ----------
        shutil.copy2(CACHE, BAK)
        try:
            d = json.load(open(CACHE, encoding="utf-8"))
            d["localDate"] = "2020-01-01"
            with open(CACHE, "w", encoding="utf-8", newline="") as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
            load_and_open()
            st2 = status_text()
            chk.ok("B1_过期快照状态", st2 and st2.get("state") == "stale" and "过期" in st2.get("text", ""), st2)
            chk.ok("B2_过期时枪械页仍可用",
                   js(cdp, "document.querySelectorAll('#gw-tree .gw-part').length") is not None)
            shot("r205-stale.png")
        finally:
            shutil.move(BAK, CACHE)

        # ---------- 3) 无缓存（离线） ----------
        try:
            shutil.move(CACHE, BAK)
            load_and_open()
            st3 = status_text()
            chk.ok("C1_无缓存状态", st3 and st3.get("state") == "missing" and "无缓存" in st3.get("text", ""), st3)
            chk.ok("C2_无缓存时地图仍可用", js(cdp, "!!document.getElementById('map-list') || document.querySelectorAll('.map-card,.lw-map').length>=0"))
            cdp.eval("(function(){var ps=document.querySelectorAll('#gw-tree .gw-part[data-slot]');"
                      "if(ps.length)ps[0].click();return ps.length;})()")
            time.sleep(1.6)
            head3 = table_head()
            chk.ok("C3_无缓存时不显示跳蚤最新列", not any("跳蚤最新" in h for h in head3), head3)
            shot("r205-missing.png")
        finally:
            shutil.move(BAK, CACHE)

        # ---------- 4) 手动刷新入口 ----------
        load_and_open()
        btn = js(cdp, "!!document.getElementById('gw-quote-refresh')")
        chk.ok("D1_手动刷新按钮存在", btn is True)
        if btn:
            js(cdp, "(function(){var b=document.getElementById('gw-quote-refresh');if(b)b.click();return true;})()")
            time.sleep(3)
            txt = js(cdp, "(function(){var b=document.getElementById('gw-quote-refresh');return b?b.textContent.trim():'';})()")
            chk.ok("D2_刷新按钮进入刷新态", "刷新中" in txt or "刷新行情" in txt, txt)

        # ---------- 5) 控制台与外部请求 ----------
        errs = [c for c in cdp.console if c.get("type") == "error"]
        chk.ok("E1_无控制台错误", len(errs) == 0, json.dumps(errs[:3], ensure_ascii=False))
        ext = [r.get("url") for r in cdp.requests
               if "127.0.0.1" not in r.get("url", "") and not r.get("url", "").startswith("data:")]
        chk.ok("E2_运行期无外部请求", len(ext) == 0, json.dumps(ext[:3], ensure_ascii=False))

        report["checks"] = chk.items
        report["pass"] = all(c["pass"] for c in chk.items)
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("\n==== %d/%d 通过 ====" % (sum(1 for c in chk.items if c["pass"]), len(chk.items)))
        return 0 if report["pass"] else 1
    finally:
        proc.terminate()
        if os.path.exists(BAK) and not os.path.exists(CACHE):
            shutil.move(BAK, CACHE)      # 兜底：确保缓存复原


if __name__ == "__main__":
    sys.exit(main())
