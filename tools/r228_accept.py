# -*- coding: utf-8 -*-
"""R228 真实浏览器验收：弹药侧栏口径按钮全部等宽。

用户原话（2026-11-10 16:55）：
  「然后子弹界面右侧的筛选按钮 我希望所有子弹的按钮都一样宽」

本脚本只认渲染结果：
  1. `.am-chips` 必须是 grid（3 列），不是 flex 自然撑开；
  2. 全部 32 个 `.am-chip` 的渲染宽度只能有一个值（容差 0.6px）；
  3. 每个分组内部同样只有一个宽度值；
  4. 同一行最多 3 个（1600 视口），侧栏不得出现横向滚动；
  5. 选中（aria-pressed=true）不改变按钮尺寸；
  6. 1000px 窄视口（侧栏变整行）下仍然只有一种宽度；
  7. 装不下的口径名必须带 title 全称，且只有 `40mm 俄制榴弹` 会出省略号；
  8. 全程无 JS 异常。

用法：python tools/r228_accept.py --port 8787 --out D:/Temp/2/r228
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


MEASURE = r"""
(function () {
  var chipsBox = document.querySelector('.am-chips');
  if (!chipsBox) { return JSON.stringify({missing: true}); }
  var cb = getComputedStyle(chipsBox);
  var all = document.querySelectorAll('.am-chip');
  var widths = [], rows = {}, clipped = [], noTitle = [], pressed = [];
  for (var i = 0; i < all.length; i++) {
    var el = all[i], r = el.getBoundingClientRect();
    var w = Math.round(r.width * 10) / 10;
    widths.push(w);
    rows[Math.round(r.top)] = (rows[Math.round(r.top)] || 0) + 1;
    if (el.scrollWidth > el.clientWidth + 1) { clipped.push(el.textContent); }
    if (!el.getAttribute('title')) { noTitle.push(el.textContent); }
    if (el.getAttribute('aria-pressed') === 'true') { pressed.push(el.textContent); }
  }
  var perGroup = [];
  var groups = document.querySelectorAll('.am-group');
  for (var g = 0; g < groups.length; g++) {
    var cs = groups[g].querySelectorAll('.am-chip'), gw = [];
    for (var j = 0; j < cs.length; j++) {
      gw.push(Math.round(cs[j].getBoundingClientRect().width * 10) / 10);
    }
    perGroup.push({g: groups[g].dataset.g, n: cs.length, widths: gw});
  }
  var rowCounts = [];
  for (var k in rows) { rowCounts.push(rows[k]); }
  var side = document.querySelector('.am-side');
  return JSON.stringify({
    display: cb.display,
    cols: cb.gridTemplateColumns,
    chipsW: Math.round(chipsBox.getBoundingClientRect().width * 10) / 10,
    n: all.length,
    widths: widths,
    perGroup: perGroup,
    maxPerRow: Math.max.apply(null, rowCounts),
    rows: rowCounts.length,
    clipped: clipped,
    noTitle: noTitle,
    pressed: pressed,
    sideOverflowX: side ? side.scrollWidth - side.clientWidth : null,
    vw: innerWidth
  });
})()
"""


def uniq(vals, tol=0.6):
    """把浮点宽度归并成簇，返回每簇代表值。"""
    out = []
    for v in sorted(vals):
        if not out or abs(v - out[-1]) > tol:
            out.append(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "docs", "r228"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9338)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    checks = []
    shots = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
        return ok

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r228-prof-%d" % os.getpid())
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
        cdp.eval("document.getElementById('view-btn-ammo').click()")
        base.wait_for(cdp, "document.querySelectorAll('.am-chip').length > 20",
                      timeout=60, label="口径按钮渲染")
        time.sleep(0.5)

        def measure():
            return json.loads(cdp.eval(MEASURE))

        def shot(name, clip=None):
            path = os.path.join(a.out, name)
            n = cdp.shot(path, clip)
            shots.append({"file": name, "bytes": n})
            return path

        # ---- 1. 默认态（1600 视口） ----
        st = measure()
        print("宽视口：n=%s display=%s cols=%s chipsW=%s" %
              (st["n"], st["display"], st["cols"], st["chipsW"]))
        check("口径容器是 grid", st["display"] == "grid", st["display"])
        check("3 列等宽轨道", st["cols"].count(" ") == 2 and len(set(st["cols"].split())) == 1,
              st["cols"])
        wu = uniq(st["widths"])
        check("全部口径按钮只有一种宽度", len(wu) == 1, "宽度簇=%s 共 %d 个" % (wu, st["n"]))
        for g in st["perGroup"]:
            gu = uniq(g["widths"])
            check("分组 %s（%d 个）内部等宽" % (g["g"], g["n"]), len(gu) == 1, gu)
        check("同一行不超过 3 个", st["maxPerRow"] <= 3, "最多 %s 个/行，共 %s 行" %
              (st["maxPerRow"], st["rows"]))
        check("侧栏无横向滚动", (st["sideOverflowX"] or 0) <= 1, st["sideOverflowX"])
        check("所有按钮都带 title 全称", not st["noTitle"], st["noTitle"])
        check("只有 40mm 俄制榴弹 出省略号（如实记录）",
              st["clipped"] in ([], ["40mm 俄制榴弹"]), st["clipped"])

        # 截图：整个分组区
        g = cdp.eval("(function(){var e=document.getElementById('am-groups');"
                     "e.scrollIntoView({block:'start'});var r=e.getBoundingClientRect();"
                     "return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
        time.sleep(0.4)
        g = cdp.eval("(function(){var e=document.getElementById('am-groups');var r=e.getBoundingClientRect();"
                     "return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
        shot("chips-1600.png", {"x": max(0, g["x"] - 8), "y": max(0, g["y"] - 8),
                                "width": g["w"] + 16,
                                "height": min(g["h"] + 16, 1000 - max(0, g["y"] - 8))})

        # ---- 2. 选中态不改变尺寸 ----
        cdp.eval("(function(){var c=document.querySelector('.am-chip');c.click();return 1;})()")
        time.sleep(0.9)
        st_sel = measure()
        check("选中一个后仍有勾选态", bool(st_sel["pressed"]), st_sel["pressed"])
        check("选中态不改变按钮宽度", len(uniq(st_sel["widths"])) == 1,
              uniq(st_sel["widths"]))
        cdp.eval("(function(){var c=document.querySelector('.am-chip');c.click();return 1;})()")
        time.sleep(0.7)

        # ---- 3. 窄视口 1000px：侧栏变整行 ----
        cdp.call("Emulation.setDeviceMetricsOverride", width=1000, height=800,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(0.9)
        st_narrow = measure()
        print("窄视口：vw=%s display=%s cols=%s" % (st_narrow["vw"], st_narrow["display"],
                                                    st_narrow["cols"]))
        check("窄视口仍是 grid", st_narrow["display"] == "grid", st_narrow["display"])
        nwu = uniq(st_narrow["widths"])
        check("窄视口全部等宽", len(nwu) == 1, nwu)
        check("窄视口侧栏无横向滚动", (st_narrow["sideOverflowX"] or 0) <= 1,
              st_narrow["sideOverflowX"])
        shot("chips-1000.png")
        cdp.call("Emulation.clearDeviceMetricsOverride")
        time.sleep(0.5)

        # ---- 4. 控制台 ----
        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "wide": st, "narrow": st_narrow,
                       "selected": st_sel}, fh, ensure_ascii=False, indent=2)

        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        print("\n宽度：%s  ·  裁切：%s" % (uniq(st["widths"]), st["clipped"]))
        ok = sum(1 for c in checks if c["ok"])
        print("%d/%d PASS" % (ok, len(checks)))
        return 0 if ok == len(checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
