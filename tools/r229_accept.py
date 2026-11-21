# -*- coding: utf-8 -*-
"""R229 真实浏览器验收：口径按钮在当前筛选下 0 发子弹时置灰。

⚠️ 已作废（R230）：用户随即澄清要的是「凡是被口径过滤掉、当前没在显示的口径
   也一律变灰，只留选中的亮着」，且要「右侧筛选按钮按下后就有变化」，不是搜索。
   R229 按不含口径过滤的池子统计的方向做反了。本脚本保留作历史记录，
   其中的「点选不改变其它口径的灰态」等断言已与新语义相反，不要再运行/据此判定。
   当前验收请用 tools/r230_accept.py。

用户原话（2026-11-10 20:02）：
  「子弹页面 右侧的筛选 我希望点击后 如果是不显示的子弹 按钮就变灰
    现在不知道哪些显示 哪些不显示」

验收口径：
  1. 每个 `.am-chip` 都带 `data-empty`（0/1），默认态记下基线；
  2. 搜索 `9x19` 后：只有 `9x19` 不灰，其余全灰（搜索只走表格内建 setSearch，
     不重绘 chips，灰态必须靠 syncAmmoChipEmpty 单独刷新）；
  3. 选中 / 取消某个口径，不得改变其它口径的灰态（统计基于 amRowsBase，
     不含口径过滤本身，否则选中一个会把其余全判空）；
  4. 逐个单独点选 32 个口径，验证 `data-empty=1` ⟺ 该口径单独筛选后 0 行；
  5. 灰态在 XP 主题下真的可见（computed opacity < 1），RESET 后恢复基线；
  6. R228 的等宽不回归；全程无 JS 异常。

用法：python tools/r229_accept.py --port 8787 --out D:/Temp/2/r229
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


STATE = r"""
(function () {
  var chips = document.querySelectorAll('.am-chip');
  var out = {}, widths = [], pressed = [], noAttr = [];
  for (var i = 0; i < chips.length; i++) {
    var c = chips[i], k = c.dataset.cal;
    out[k] = c.dataset.empty;
    widths.push(Math.round(c.getBoundingClientRect().width * 10) / 10);
    if (c.getAttribute('aria-pressed') === 'true') { pressed.push(k); }
    if (c.dataset.empty !== '0' && c.dataset.empty !== '1') { noAttr.push(k); }
  }
  var emptyOpacity = null, normalOpacity = null;
  for (var j = 0; j < chips.length; j++) {
    var o = parseFloat(getComputedStyle(chips[j]).opacity);
    if (chips[j].dataset.empty === '1' && chips[j].getAttribute('aria-pressed') !== 'true'
        && emptyOpacity === null) { emptyOpacity = o; }
    if (chips[j].dataset.empty === '0' && normalOpacity === null) { normalOpacity = o; }
  }
  var count = document.getElementById('am-count');
  var rows = document.querySelectorAll('#am-table .tbl-row').length;
  var emptyRow = document.querySelector('#am-table .tbl-empty');
  return JSON.stringify({
    n: chips.length, empty: out,
    emptyKeys: Object.keys(out).filter(function (k) { return out[k] === '1'; }),
    normalKeys: Object.keys(out).filter(function (k) { return out[k] === '0'; }),
    noAttr: noAttr, pressed: pressed,
    widths: widths,
    emptyOpacity: emptyOpacity, normalOpacity: normalOpacity,
    count: count ? (count.textContent || '').trim() : null,
    rows: rows,
    emptyText: emptyRow ? (emptyRow.textContent || '').trim() : '',
    search: (document.getElementById('am-search') || {}).value || ''
  });
})()
"""


def uniq(vals, tol=0.6):
    out = []
    for v in sorted(vals):
        if not out or abs(v - out[-1]) > tol:
            out.append(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "docs", "r229"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9339)
    ap.add_argument("--skip-each", action="store_true", help="跳过 32 个口径逐个点选的一致性验证")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    checks = []
    shots = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
        return ok

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r229-prof-%d" % os.getpid())
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
        time.sleep(0.6)

        def read():
            return json.loads(cdp.eval(STATE))

        def shown(st):
            """工具栏 `N / 200 件` 里的 N。空态行也带 .tbl-row，不能只读 DOM 行数。"""
            try:
                return int((st.get("count") or "").split("/")[0].strip())
            except (ValueError, AttributeError):
                return st["rows"]

        def set_search(q):
            cdp.eval("(function(){var e=document.getElementById('am-search');"
                     "e.value=%s;e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()"
                     % json.dumps(q, ensure_ascii=False))
            time.sleep(0.55)

        def click_cal(k):
            cdp.eval("(function(){var e=document.querySelector('.am-chip[data-cal=%s]');"
                     "if(e){e.click();}return 1;})()" % json.dumps(k, ensure_ascii=False))
            time.sleep(0.28)

        def shot(name, clip=None):
            path = os.path.join(a.out, name)
            shots.append({"file": name, "bytes": cdp.shot(path, clip)})

        def group_clip():
            cdp.eval("document.getElementById('am-groups').scrollIntoView({block:'start'})")
            time.sleep(0.35)
            return cdp.eval("(function(){var e=document.getElementById('am-groups');"
                            "var r=e.getBoundingClientRect();"
                            "return {x:r.x,y:r.y,w:r.width,h:r.height};})()")

        # ---- 1. 默认态 ----
        st = read()
        print("默认：chips=%s 灰=%s 亮=%s count=%s" %
              (st["n"], len(st["emptyKeys"]), len(st["normalKeys"]), st["count"]))
        check("每个口径按钮都带 data-empty", st["n"] == 32 and not st["noAttr"], st["noAttr"])
        check("R228 等宽不回归", len(uniq(st["widths"])) == 1, uniq(st["widths"]))
        base_empty = set(st["emptyKeys"])
        shot("default.png", None)
        b = group_clip()
        shot("chips-default.png", {"x": max(0, b["x"] - 8), "y": max(0, b["y"] - 8),
                                   "width": b["w"] + 16,
                                   "height": min(b["h"] + 16, 1000 - max(0, b["y"] - 8))})

        # ---- 2. 搜索 9x19：只走 setSearch，灰态必须同步 ----
        set_search("9x19")
        s9 = read()
        print("搜索 9x19：亮=%s 灰=%d count=%s rows=%s" %
              (s9["normalKeys"], len(s9["emptyKeys"]), s9["count"], s9["rows"]))
        check("搜索后只剩 9x19 不灰", s9["normalKeys"] == ["9x19"], s9["normalKeys"])
        check("搜索后 9x19 仍有子弹", "9x19" in s9["normalKeys"] and s9["rows"] > 0,
              "rows=%s count=%s" % (s9["rows"], s9["count"]))
        check("灰态在 XP 主题下可见（opacity<1）",
              s9["emptyOpacity"] is not None and s9["emptyOpacity"] < 0.9
              and s9["normalOpacity"] is not None and s9["normalOpacity"] >= 0.99,
              "empty=%s normal=%s" % (s9["emptyOpacity"], s9["normalOpacity"]))
        b = group_clip()
        shot("chips-search-9x19.png", {"x": max(0, b["x"] - 8), "y": max(0, b["y"] - 8),
                                       "width": b["w"] + 16,
                                       "height": min(b["h"] + 16, 1000 - max(0, b["y"] - 8))})

        # ---- 3. 点选一个已灰的口径：其它灰态不变 ----
        click_cal("5.45x39")
        s_sel = read()
        check("点选不改变其它口径的灰态", set(s_sel["emptyKeys"]) == set(s9["emptyKeys"]),
              "changed=%s" % (set(s_sel["emptyKeys"]) ^ set(s9["emptyKeys"])))
        check("点中的口径仍是按下态且仍灰",
              "5.45x39" in s_sel["pressed"] and s_sel["empty"]["5.45x39"] == "1",
              "pressed=%s empty=%s" % (s_sel["pressed"], s_sel["empty"].get("5.45x39")))
        check("选中后表格确实 0 行", shown(s_sel) == 0 and s_sel["emptyText"] != "",
              "count=%s rows=%s emptyText=%s" %
              (s_sel["count"], s_sel["rows"], s_sel["emptyText"]))
        click_cal("5.45x39")   # 取消

        # ---- 4. 清空搜索恢复基线 ----
        set_search("")
        s_back = read()
        check("清搜索后灰态回到默认基线", set(s_back["emptyKeys"]) == base_empty,
              "now=%s base=%s" % (sorted(s_back["emptyKeys"]), sorted(base_empty)))

        # ---- 5. 加一个区间筛选，逐个点选验证 empty ⟺ 单独选中后 0 行 ----
        # PEN≥40：让「亮」和「灰」都有一定数量，逐个点选的对照才有覆盖力
        cdp.eval("(function(){var e=document.querySelector('.am-num[data-range=pen][data-bound=min]');"
                 "e.value='40';e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()")
        time.sleep(0.7)
        pen = read()
        print("PEN≥40：灰=%d 亮=%d 表格=%s" %
              (len(pen["emptyKeys"]), len(pen["normalKeys"]), pen["count"]))
        check("区间筛选后部分口径变灰、部分仍亮",
              0 < len(pen["emptyKeys"]) < pen["n"], "灰=%d/%d" % (len(pen["emptyKeys"]), pen["n"]))
        b = group_clip()
        shot("chips-pen40.png", {"x": max(0, b["x"] - 8), "y": max(0, b["y"] - 8),
                                 "width": b["w"] + 16,
                                 "height": min(b["h"] + 16, 1000 - max(0, b["y"] - 8))})

        mismatches = []
        if not a.skip_each:
            for k in sorted(pen["empty"].keys()):
                click_cal(k)
                one = read()
                n = shown(one)
                has_rows = n > 0
                is_empty = pen["empty"][k] == "1"
                if has_rows == is_empty:
                    mismatches.append({"cal": k, "empty": pen["empty"][k], "shown": n})
                click_cal(k)
            check("32 个口径逐个点选：灰 ⟺ 单独筛选后 0 行",
                  not mismatches, json.dumps(mismatches[:6], ensure_ascii=False))
        else:
            print("（--skip-each：跳过逐个点选）")

        # ---- 6. RESET 恢复 ----
        cdp.eval("document.getElementById('am-reset').click()")
        time.sleep(0.8)
        s_reset = read()
        check("RESET 后灰态回到默认基线", set(s_reset["emptyKeys"]) == base_empty,
              "now=%s base=%s" % (sorted(s_reset["emptyKeys"]), sorted(base_empty)))
        check("RESET 后无按下态", not s_reset["pressed"], s_reset["pressed"])

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "default": st, "search9x19": s9,
                       "selected": s_sel, "pen80": pen, "reset": s_reset,
                       "mismatches": mismatches}, fh, ensure_ascii=False, indent=2)
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
