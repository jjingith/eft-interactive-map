# -*- coding: utf-8 -*-
"""R20.5c 真实浏览器验收：参考站 db4tarkov 对齐项（口径色块 / 密集网格 / 浏览页价格口径 / 清空 / 回退）。"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r20.5", "local-screenshots")


def js(cdp, expr):
    r = cdp.eval(expr)
    if isinstance(r, str) and r.strip()[:1] in ("{", "["):
        try:
            return json.loads(r)
        except Exception:  # noqa: BLE001
            return r
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8806")
    ap.add_argument("--port", type=int, default=9730)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    checks = []

    def ok(cid, cond, detail=""):
        checks.append({"id": cid, "pass": bool(cond), "detail": str(detail)[:400]})
        print(("PASS " if cond else "FAIL ") + cid + ("  " + str(detail)[:220] if detail else ""))

    # 每轮独立 profile：视图模式（口径/工作台…）会存进 localStorage，复用 profile 会串味
    prof = os.path.join(tempfile.gettempdir(), "r205caccept%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Page.navigate", url=args.base + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(6)
        cdp.eval("(function(){var b=document.querySelector('[data-view=gun]');if(b)b.click();return !!b;})()")
        time.sleep(2.5)
        # 显式切到「口径」浏览页（视图模式会被持久化，不能依赖上一轮状态）
        cdp.eval("(function(){var t=document.querySelector('.gw-mode[data-gwmode=caliber]');"
                 "if(t)t.click();return !!t;})()")
        time.sleep(3)

        # ---------------- L1 浏览页价格口径 pills
        pills = js(cdp, "(function(){return [].slice.call(document.querySelectorAll('#gw-browseprices .gw-price-pill'))"
                        ".map(function(x){return (x.dataset.mode||'')+'|'+(x.textContent||'').trim()+'|'+x.disabled;});})()")
        ok("L1_浏览页有价格口径切换", isinstance(pills, list) and len(pills) >= 3, pills)

        # ---------------- L2 口径色块 + 配色来自真实弹药类别
        blocks = js(cdp, """(function(){var out=[];document.querySelectorAll('#gw-browse .gw-calblock').forEach(function(b){
             out.push({cal:(b.querySelector('.gw-calblock-name')||{}).textContent||'',
                       cls:b.className,
                       n:(b.querySelector('.gw-calblock-n')||{}).textContent||''});});
             return JSON.stringify(out);})()""")
        blocks = blocks if isinstance(blocks, list) else []
        ok("L2_每个口径分组都有左侧色块", len(blocks) >= 20, "色块数=%d" % len(blocks))
        cats = {}
        for b in blocks:
            for c in b.get("cls", "").split():
                if c.startswith("gw-calcat-"):
                    cats[c] = cats.get(c, 0) + 1
        ok("L2b_色块按真实弹药类别着色", len(cats) >= 3, cats)
        # 抽样核对：5.56x45 应为 rifle 色
        sample = next((b for b in blocks if "5.56x45" in b.get("cal", "")), None)
        ok("L2c_5.56x45标为步枪弹色", sample is not None and "gw-calcat-rifle" in sample.get("cls", ""), sample)

        # ---------------- L3 密集网格（每行卡片数）
        # 布局可能在懒加载/重排后仍在变化：轮询到稳定再判定
        dens = {}
        for _ in range(12):
            dens = js(cdp, """(function(){var g=document.querySelectorAll('#gw-browse .gw-browse-group');
                 var best=0;g.forEach(function(x){var c=x.querySelectorAll('.gw-card').length;if(c>best)best=c;});
                 var gr=document.querySelector('#gw-browse .gw-browse-grid');
                 var cols=gr?getComputedStyle(gr).gridTemplateColumns.split(' ').length:0;
                 var w=gr?Math.round(gr.getBoundingClientRect().width):0;
                 var cw=0;var c0=g[0]?g[0].querySelector('.gw-card'):null;
                 if(c0)cw=Math.round(c0.getBoundingClientRect().width);
                 return JSON.stringify({maxCardsInGroup:best, cols:cols, gridW:w, cardW:cw,
                                       innerW:innerWidth});})()""")
            if isinstance(dens, dict) and dens.get("cols", 0) >= 8:
                break
            time.sleep(0.6)
        ok("L3_网格已变密集(列数≥10)", isinstance(dens, dict) and dens.get("cols", 0) >= 10, dens)

        # ---------------- L4 浏览页价格口径切换生效
        before = js(cdp, """(function(){var p=document.querySelector('#gw-browse .gw-card-price');
             return p?(p.textContent||'').trim():'' ;})()""")
        js(cdp, """(function(){var b=document.querySelector('#gw-browseprices .gw-price-pill[data-mode=base]');
             if(b && !b.disabled){b.click();return 'clicked';} return 'no-btn';})()""")
        time.sleep(2.5)
        after = js(cdp, """(function(){var p=document.querySelector('#gw-browse .gw-card-price');
             return p?(p.textContent||'').trim():'' ;})()""")
        ok("L4_浏览页切换口径后卡片价格随之变化", before != after, "%s -> %s" % (before, after))

        # 切回 FLEA
        js(cdp, """(function(){var b=document.querySelector('#gw-browseprices .gw-price-pill[data-mode=flea]');
             if(b && !b.disabled){b.click();return 'clicked';} return 'no-btn';})()""")
        time.sleep(2)

        # ---------------- L5/L6 工作台：清空配件 + 回退
        cdp.eval("(function(){var c=document.querySelector('#gw-browse .gw-card');if(c)c.click();return !!c;})()")
        time.sleep(4)
        installed0 = js(cdp, "(function(){return document.querySelectorAll('#gw-tree .gw-part[data-item]').length;})()")
        ok("L5a_已选枪后有已装配件", isinstance(installed0, int) and installed0 > 0, "已装=%s" % installed0)
        js(cdp, "(function(){var b=document.getElementById('gw-clearall');if(b)b.click();return !!b;})()")
        time.sleep(2.5)
        installed1 = js(cdp, "(function(){return document.querySelectorAll('#gw-tree .gw-part[data-item]').length;})()")
        ok("L5b_清空配件生效", isinstance(installed1, int) and installed1 < installed0,
           "%s -> %s" % (installed0, installed1))
        undone = js(cdp, "(function(){var b=document.getElementById('gw-undo');if(!b)return 'no-btn';"
                         "if(b.disabled)return 'disabled';b.click();return 'clicked';})()")
        time.sleep(2.5)
        installed2 = js(cdp, "(function(){return document.querySelectorAll('#gw-tree .gw-part[data-item]').length;})()")
        ok("L6_回退恢复装配", undone == "clicked" and isinstance(installed2, int) and installed2 > installed1,
           "%s：%s -> %s" % (undone, installed1, installed2))

        # ---------------- L7 控制台与网络
        errs = [c for c in cdp.console if c.get("level") in ("error",)]
        ok("L7a_控制台无错误", not errs, errs[:2])
        hosts = sorted(set(r.get("host", "") for r in cdp.requests))
        ext = [h for h in hosts if h and h not in ("127.0.0.1", "localhost")]
        ok("L7b_运行期无外部网络请求", not ext, ext[:5])

        r = cdp.call("Page.captureScreenshot", format="png")
        with open(os.path.join(OUT, "04-r205c-builder.png"), "wb") as f:
            f.write(base64.b64decode(r["data"]))

        rep = {"validator": "r205c_accept.py", "base": args.base,
               "pass": all(c["pass"] for c in checks),
               "summary": {"total": len(checks),
                           "passed": sum(1 for c in checks if c["pass"])},
               "checks": checks,
               "consoleErrors": len(errs),
               "externalHosts": ext}
        out = os.path.join(ROOT, "docs", "r20.5", "browser-accept.r20.5c.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print("\n==== %d/%d 通过（报告：%s）====" % (rep["summary"]["passed"], rep["summary"]["total"], out))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
