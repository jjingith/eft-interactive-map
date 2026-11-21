# -*- coding: utf-8 -*-
"""R231 验收：弹药页空结果时，表格背后不再出现被拉伸放大的位图边框。

用户原话（2026-11-10 20:41）：
  「我发现把所有子弹隐藏后 子弹页面背后的背景好像是什么图强行放大后的样子 请改掉」

根因：assets/xp-ui/xp-ui-app.css 里三个工作台共用的
  `border-image: url("table-frame.png") 2 fill / 2px stretch !important`
table-frame.png 只有 64×64，`fill` 把中间那圈细内框线一起 stretch 到整块
1280×700 的滚动区，变成模糊灰带。有行时被行盖住，全筛掉后才露出来。

修法：弹药页从这条共用规则里摘出，改用 #fff + 1px 实线
（与 theme-windows-xp.css 的列表视图口径一致）；配装 / 枪匠保持原样。

用法：python tools/r231_accept.py --port 8787 --out D:/Temp/2/r231
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


def table_state(cdp, sel):
    expr = r"""
(function(){
  var e = document.querySelector(%s);
  if (!e) { return JSON.stringify({missing:true}); }
  var c = getComputedStyle(e), r = e.getBoundingClientRect();
  return JSON.stringify({
    borderImg: c.borderImageSource,
    borderW: c.borderTopWidth,
    bgColor: c.backgroundColor,
    w: Math.round(r.width), h: Math.round(r.height),
    rows: e.querySelectorAll('.tbl-row').length,
    empty: !!e.querySelector('.tbl-empty')
  });
})()
""" % json.dumps(sel)
    return json.loads(cdp.eval(expr))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r231"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9341)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    checks = []
    shots = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
        return ok

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r231-prof-%d" % os.getpid())
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

        def shot(name):
            b = cdp.eval("(function(){var e=document.querySelector('.am-main');"
                         "if(!e){return null;}var r=e.getBoundingClientRect();"
                         "return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
            if not b:
                return
            path = os.path.join(a.out, name)
            shots.append({"file": name, "bytes": cdp.shot(path, {
                "x": max(0, b["x"]), "y": max(0, b["y"]), "width": b["w"],
                "height": min(b["h"], 1000 - max(0, b["y"]))})})

        # ---- CSS 静态：弹药页不再共用 fill 拉伸 ----
        css = open(os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css"), encoding="utf-8").read()
        rule = css[css.index("/* 表格滚区："):css.index("/* 枪匠顶部")]
        check("共用位图规则里已摘掉弹药页",
              ".am-workbench .am-table .tbl-scroll" not in rule.split("/* R231")[0], rule[:200])
        check("弹药页改用 1px 实线 + 白底",
              "html body .am-workbench .am-table .tbl-scroll" in rule
              and "border: 1px solid var(--xp-border-dark" in rule
              and "background-color: #fff !important" in rule)
        check("配装 / 枪匠仍用 table-frame.png",
              "table-frame.png" in rule and ".gun-workbench .tbl-scroll" in rule
              and ".loadout-workbench .tbl-scroll" in rule)

        # ---- 弹药页有数据 ----
        cdp.eval("document.getElementById('view-btn-ammo').click()")
        base.wait_for(cdp, "document.querySelectorAll('#am-table .tbl-row').length > 50",
                      timeout=60, label="弹药表格渲染")
        time.sleep(0.4)
        t_normal = table_state(cdp, ".am-workbench .am-table .tbl-scroll")
        print("有数据：", t_normal)
        check("有数据时表格滚区无位图边框",
              t_normal.get("borderImg") == "none", t_normal.get("borderImg"))
        check("有数据时是 1px 实线 + 白底",
              t_normal.get("borderW") == "1px" and t_normal.get("bgColor") == "rgb(255, 255, 255)",
              (t_normal.get("borderW"), t_normal.get("bgColor")))
        shot("01-normal.png")

        # ---- 全部子弹隐藏 ----
        cdp.eval("(function(){var e=document.getElementById('am-search');e.value='zzzzzz';"
                 "e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()")
        time.sleep(0.9)
        t_empty = table_state(cdp, ".am-workbench .am-table .tbl-scroll")
        count = cdp.eval("(document.getElementById('am-count')||{}).textContent")
        print("空结果：", t_empty, "count=", count)
        check("确实全部隐藏（0 件且显示空态行）",
              t_empty.get("empty") and "0 /" in (count or ""), count)
        check("空结果时仍无被拉伸的位图",
              t_empty.get("borderImg") == "none", t_empty.get("borderImg"))
        check("空结果时滚动区仍是 1px 白底（没有灰带）",
              t_empty.get("borderW") == "1px" and t_empty.get("bgColor") == "rgb(255, 255, 255)",
              (t_empty.get("borderW"), t_empty.get("bgColor")))
        shot("02-empty-fixed.png")

        # ---- 其它工作台不回归 ----
        for view, sel, label in (
            ("view-btn-gun", ".gun-workbench .tbl-scroll", "枪匠"),
            ("view-btn-loadout", ".loadout-workbench .tbl-scroll", "配装"),
        ):
            cdp.eval("document.getElementById(%s).click()" % json.dumps(view))
            time.sleep(1.2)
            t = table_state(cdp, sel)
            print(label, t)
            check("%s 表格滚区仍用 table-frame.png（未回归）" % label,
                  "table-frame.png" in (t.get("borderImg") or ""), t.get("borderImg"))

        # ---- 回到弹药页：R228/R230 不回归 ----
        cdp.eval("document.getElementById('view-btn-ammo').click()")
        time.sleep(0.5)
        # 清空前面留下的搜索词，否则按 R230 语义 32 个口径会全部（正确地）置灰
        cdp.eval("(function(){var e=document.getElementById('am-search');e.value='';"
                 "e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()")
        time.sleep(0.6)
        chips = cdp.eval("(function(){var a=document.querySelectorAll('.am-chip');"
                         "var w=[];for(var i=0;i<a.length;i++){w.push(Math.round(a[i].getBoundingClientRect().width*10)/10);}"
                         "return {n:a.length, uniq:Array.from(new Set(w)), "
                         "lit:document.querySelectorAll('.am-chip[data-empty=\"0\"]').length};})()")
        print("回到弹药：", chips)
        check("口径按钮等宽 + 默认全亮不回归",
              chips["n"] == 32 and len(chips["uniq"]) == 1 and chips["lit"] == 32, chips)

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "normal": t_normal,
                       "empty": t_empty, "chips": chips}, fh, ensure_ascii=False, indent=2)
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
