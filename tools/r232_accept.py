# -*- coding: utf-8 -*-
"""R232 验收：所有视图的表格滚动区都不再被小位图 fill 拉伸。

用户原话（2026-11-10 21:16）：
  「你检查一下 我发现好几个地方都会有而是表格滚动区的边框位图被放大」

R231 只摘掉了弹药页；R232 排查发现同类问题还有：
  - `table-frame.png`(64×64) `2 fill / 2px stretch` → 配装 / 枪匠 / 隐藏模板
  - `groupbox.png`(280×154) `6 fill / 2px stretch` → 通用 html body .tbl-scroll
两条 fill 规则从源头摘掉，所有 .tbl-scroll 回落到纯色 + 1px 实线。

用法：python tools/r232_accept.py --port 8787 --out D:/Temp/2/r232
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS = ("map", "tasks", "ammo", "gun", "loadout", "market")

SCROLLS = r"""
(function(){
  var out = [];
  document.querySelectorAll('.tbl-scroll').forEach(function(e, i){
    var c = getComputedStyle(e), r = e.getBoundingClientRect();
    out.push({i:i, cls:String(e.className||'').slice(0,60), id:e.id,
      src:(c.borderImageSource.match(/[^/"']+\.png/)||[''])[0],
      slice:c.borderImageSlice, biw:c.borderImageWidth,
      borderW:c.borderTopWidth, bg:c.backgroundColor,
      w:Math.round(r.width), h:Math.round(r.height),
      visible: !!(e.offsetParent || e.getClientRects().length)});
  });
  return JSON.stringify(out);
})()
"""

# 体检：仍在使用 fill 位图的大容器（记录用，不属于本轮修改范围）
FILLS = r"""
(function(){
  var out = [], seen = {};
  document.querySelectorAll('*').forEach(function(e){
    var c = getComputedStyle(e);
    if (!c.borderImageSource || c.borderImageSource === 'none') { return; }
    if (c.display === 'none' || c.visibility === 'hidden') { return; }
    var r = e.getBoundingClientRect();
    if (r.width < 250 && r.height < 200) { return; }
    if ((c.borderImageSlice||'').indexOf('fill') < 0) { return; }
    var src = (c.borderImageSource.match(/[^/"']+\.png/)||[''])[0];
    var key = src + '|' + String(e.className||'').slice(0,30);
    if (seen[key]) { return; }
    seen[key] = 1;
    out.push({src:src, cls:String(e.className||'').slice(0,40),
              w:Math.round(r.width), h:Math.round(r.height)});
  });
  return JSON.stringify(out);
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r232"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9342)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    checks, shots, per_view = [], [], {}

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:380]})
        return ok

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r232-prof-%d" % os.getpid())
    proc = None
    try:
        proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % a.port)
        if not base.wait_ready(cdp, "index.html", timeout=60):
            raise SystemExit("页面没打开")
        time.sleep(2.2)

        # ---- CSS 静态：两条 fill 规则已从源头摘掉 ----
        css = open(os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css"), encoding="utf-8").read()
        import re
        decl = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        check("table-frame.png 不再出现在任何 CSS 声明里", "table-frame.png" not in decl)
        i = css.index("html body #lw-cost,")
        group = re.sub(r"/\*.*?\*/", "", css[i:css.index("/* --- 15.3", i)], flags=re.S)
        check("groupbox.png 通用组里不再含 .tbl-scroll", ".tbl-scroll" not in group, group[:160])

        # ---- 逐视图扫描 .tbl-scroll ----
        all_scrolls = []
        fills_by_view = {}
        for v in VIEWS:
            cdp.eval("document.getElementById(%s).click()" % json.dumps("view-btn-" + v))
            time.sleep(1.0 if v != "market" else 1.6)
            scrolls = json.loads(cdp.eval(SCROLLS))
            per_view[v] = scrolls
            all_scrolls.extend([dict(s, view=v) for s in scrolls])
            fills_by_view[v] = json.loads(cdp.eval(FILLS))
            print("%-8s tbl-scroll=%d  %s" % (
                v, len(scrolls),
                [(s["src"] or "none", s["w"], s["h"]) for s in scrolls]))
            path = os.path.join(a.out, "view-%s.png" % v)
            shots.append({"file": os.path.basename(path), "bytes": cdp.shot(path)})

        bad_src = [s for s in all_scrolls if s["src"]]
        check("全部 %d 个视图的 .tbl-scroll 都没有 fill 位图" % len(all_scrolls),
              not bad_src, json.dumps(bad_src[:4], ensure_ascii=False))
        visible = [s for s in all_scrolls if s["visible"] and s["w"] > 2 and s["h"] > 2]
        print("可见表格滚区：", [(s["view"], s["w"], s["h"], s["borderW"], s["bg"]) for s in visible])
        check("可见滚区都是 1px 实线", all(s["borderW"] == "1px" for s in visible),
              [(s["view"], s["borderW"]) for s in visible])
        check("可见滚区都是不透明纯色底",
              all(s["bg"].startswith("rgb(") and "rgba" not in s["bg"] for s in visible),
              [(s["view"], s["bg"]) for s in visible])
        check("各视图确实都有表格滚区（不是空跑）", len(all_scrolls) >= 6, len(all_scrolls))

        # ---- 配装页空结果：不再有放大灰带 ----
        cdp.eval("document.getElementById('view-btn-loadout').click()")
        time.sleep(1.0)
        lw = json.loads(cdp.eval(SCROLLS))
        big = [s for s in lw if s["w"] > 500]
        check("配装页大表格滚区无位图 / 1px 白底",
              big and all(s["src"] == "" and s["borderW"] == "1px"
                          and s["bg"] == "rgb(255, 255, 255)" for s in big), big)
        # 空态对照：把表格行清空后截图（只改 DOM 展示，不写数据）
        b = cdp.eval("(function(){var e=document.querySelector('.loadout-workbench .tbl-scroll');"
                     "if(!e){return null;}var r=e.getBoundingClientRect();"
                     "return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
        if b:
            cdp.shot(os.path.join(a.out, "loadout-table.png"),
                     {"x": max(0, b["x"]), "y": max(0, b["y"]),
                      "width": b["w"], "height": min(b["h"], 1000 - max(0, b["y"]))})

        # ---- R228/R230/R231 不回归 ----
        cdp.eval("document.getElementById('view-btn-ammo').click()")
        time.sleep(0.9)
        ammo = json.loads(cdp.eval(SCROLLS))
        abig = [s for s in ammo if s["w"] > 500]
        check("R231 弹药滚区仍无位图 / 1px 白底",
              abig and all(s["src"] == "" and s["borderW"] == "1px" for s in abig), abig)
        chips = cdp.eval("(function(){var a=document.querySelectorAll('.am-chip');"
                         "var w=[];for(var i=0;i<a.length;i++){w.push(Math.round(a[i].getBoundingClientRect().width*10)/10);}"
                         "return {n:a.length, uniq:Array.from(new Set(w)), "
                         "lit:document.querySelectorAll('.am-chip[data-empty=\"0\"]').length};})()")
        check("R228 等宽 / R230 默认全亮不回归",
              chips["n"] == 32 and len(chips["uniq"]) == 1 and chips["lit"] == 32, chips)

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "perView": per_view,
                       "remainingFillContainers": fills_by_view}, fh, ensure_ascii=False, indent=2)
        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        ok = sum(1 for c in checks if c["ok"])
        print("\n%d/%d PASS" % (ok, len(checks)))
        return 0 if ok == len(checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
