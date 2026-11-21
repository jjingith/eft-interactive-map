# -*- coding: utf-8 -*-
"""R230 真实浏览器验收：口径按钮「亮 = 当前显示在表格里」，按下后立即变化。

用户原话（2026-11-10 20:22 / 20:23）：
  「凡是被口径过滤掉、当前没在显示的口径也一律变灰，只留选中的亮着 要的就是这个啊」
  「而且你现在做的是搜索 我要的是右侧的筛选按钮 按下后就有变化」

R229 做反了：按 amRowsBase()（不含口径过滤）统计，于是点口径按钮时其它按钮不变。
R230 改为按最终显示行 amFilterByCal(pool) 统计：
  - 没选口径时：所有有子弹的口径都亮，0 发的灰；
  - 选中若干口径时：只有那几个（且确实有子弹）亮，其余一律灰；
  - 被选中但被其它条件筛成 0 发的口径仍灰，title 说明原因。

验收全部走真实点击，不依赖搜索框作为触发源。
用法：python tools/r230_accept.py --port 8787 --out D:/Temp/2/r230
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
  var lit = [], grey = [], titles = {}, widths = [], pressed = [];
  for (var i = 0; i < chips.length; i++) {
    var c = chips[i], k = c.dataset.cal;
    if (c.dataset.empty === '1') { grey.push(k); } else { lit.push(k); }
    titles[k] = c.title || '';
    widths.push(Math.round(c.getBoundingClientRect().width * 10) / 10);
    if (c.getAttribute('aria-pressed') === 'true') { pressed.push(k); }
  }
  var greyOpacity = null, litOpacity = null;
  for (var j = 0; j < chips.length; j++) {
    var o = parseFloat(getComputedStyle(chips[j]).opacity);
    if (chips[j].dataset.empty === '1' && greyOpacity === null) { greyOpacity = o; }
    if (chips[j].dataset.empty === '0' && litOpacity === null) { litOpacity = o; }
  }
  var count = document.getElementById('am-count');
  return JSON.stringify({
    n: chips.length, lit: lit, grey: grey, titles: titles,
    widths: widths, pressed: pressed,
    greyOpacity: greyOpacity, litOpacity: litOpacity,
    count: count ? (count.textContent || '').trim() : null,
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
        os.path.abspath(__file__))), "docs", "r230"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9340)
    ap.add_argument("--skip-each", action="store_true", help="跳过 32 个口径逐个点选")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    checks = []
    shots = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
        return ok

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r230-prof-%d" % os.getpid())
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
            try:
                return int((st.get("count") or "").split("/")[0].strip())
            except (ValueError, AttributeError):
                return -1

        def click_cal(k):
            cdp.eval("(function(){var e=document.querySelector('.am-chip[data-cal=%s]');"
                     "if(e){e.click();}return 1;})()" % json.dumps(k, ensure_ascii=False))
            time.sleep(0.3)

        def click_show(g):
            cdp.eval("(function(){var e=document.querySelector('.am-show[data-g=%s]');"
                     "if(e){e.click();}return 1;})()" % json.dumps(g))
            time.sleep(0.45)

        def set_search(q):
            cdp.eval("(function(){var e=document.getElementById('am-search');"
                     "e.value=%s;e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()"
                     % json.dumps(q, ensure_ascii=False))
            time.sleep(0.5)

        def reset():
            cdp.eval("document.getElementById('am-reset').click()")
            time.sleep(0.6)

        def shot(name):
            cdp.eval("document.getElementById('am-groups').scrollIntoView({block:'start'})")
            time.sleep(0.35)
            b = cdp.eval("(function(){var e=document.getElementById('am-groups');"
                         "var r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
            path = os.path.join(a.out, name)
            shots.append({"file": name, "bytes": cdp.shot(path, {
                "x": max(0, b["x"] - 8), "y": max(0, b["y"] - 8),
                "width": b["w"] + 16,
                "height": min(b["h"] + 16, 1000 - max(0, b["y"] - 8))})})

        # ---- 1. 默认态：不点任何东西 ----
        st = read()
        print("默认：n=%s 亮=%d 灰=%d count=%s" % (st["n"], len(st["lit"]), len(st["grey"]), st["count"]))
        check("默认 32 个按钮全亮", st["n"] == 32 and len(st["lit"]) == 32, st["grey"])
        check("R228 的 90px 等宽不回归", len(uniq(st["widths"])) == 1, uniq(st["widths"]))
        shot("01-default.png")

        # ---- 2. 用户要的核心：按下右侧口径按钮，立刻只留它亮 ----
        click_cal("9x19")
        c1 = read()
        print("点 9x19 后：亮=%s 灰=%d count=%s" % (c1["lit"], len(c1["grey"]), c1["count"]))
        check("按下口径按钮后立刻只剩它亮", c1["lit"] == ["9x19"], c1["lit"])
        check("其余 31 个全部变灰", len(c1["grey"]) == 31, len(c1["grey"]))
        check("被点按钮是按下态", c1["pressed"] == ["9x19"], c1["pressed"])
        check("灰按钮 title 说明是「未选中」", "当前未选中" in (c1["titles"].get("5.45x39") or ""),
              c1["titles"].get("5.45x39"))
        check("灰态在 XP 主题下可见", c1["greyOpacity"] is not None and c1["greyOpacity"] < 0.9
              and c1["litOpacity"] is not None and c1["litOpacity"] >= 0.99,
              "grey=%s lit=%s" % (c1["greyOpacity"], c1["litOpacity"]))
        check("表格只显示 9x19（9 发）", shown(c1) == 9, c1["count"])
        shot("02-click-9x19.png")

        # ---- 3. 多选：两个亮 ----
        click_cal("5.45x39")
        c2 = read()
        check("再点一个 → 两个都亮，其余 30 灰",
              set(c2["lit"]) == {"9x19", "5.45x39"} and len(c2["grey"]) == 30,
              "lit=%s grey=%d" % (c2["lit"], len(c2["grey"])))
        check("表格行数 = 两个口径之和", shown(c2) > shown(c1), "%s → %s" % (c1["count"], c2["count"]))
        shot("03-two-selected.png")

        # ---- 4. 取消一个：只剩另一个 ----
        click_cal("9x19")
        c3 = read()
        check("再点一次取消 → 只剩 5.45x39 亮", c3["lit"] == ["5.45x39"], c3["lit"])
        check("表格随取消收回", shown(c3) < shown(c2), "%s → %s" % (c2["count"], c3["count"]))

        # ---- 5. SHOW 整组 ----
        reset()
        click_show("pistol")
        c4 = read()
        check("SHOW 整组后只亮该组口径",
              0 < len(c4["lit"]) < 32 and set(c4["pressed"]) == set(c4["lit"]),
              "lit=%s pressed=%s" % (c4["lit"], c4["pressed"]))
        print("SHOW pistol：亮=%s" % c4["lit"])
        shot("04-show-pistol.png")

        # ---- 6. 被选中但 0 发：仍然灰，且 title 说明 0 发 ----
        reset()
        set_search("9x19")
        click_cal("5.45x39")
        c5 = read()
        check("选中一个 0 发的口径：它仍然灰（亮=确实显示）",
              "5.45x39" not in c5["lit"] and c5["titles"].get("5.45x39", "").find("0 发") >= 0,
              "lit=%s title=%s" % (c5["lit"], c5["titles"].get("5.45x39")))
        check("此时表格 0 行", shown(c5) == 0, c5["count"])
        shot("05-selected-but-zero.png")

        # ---- 7. RESET 恢复 ----
        reset()
        set_search("")
        c6 = read()
        check("RESET 后 32 个全亮、无按下态",
              len(c6["lit"]) == 32 and not c6["pressed"],
              "grey=%s pressed=%s" % (c6["grey"], c6["pressed"]))

        # ---- 8. 区间筛选（无选中）：0 发口径灰 ----
        cdp.eval("(function(){var e=document.querySelector('.am-num[data-range=pen][data-bound=min]');"
                 "e.value='40';e.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()")
        time.sleep(0.7)
        pen = read()
        print("PEN≥40（无选中）：亮=%d 灰=%d 表格=%s" %
              (len(pen["lit"]), len(pen["grey"]), pen["count"]))
        check("区间筛选后部分口径因 0 发变灰", 0 < len(pen["grey"]) < pen["n"],
              "灰=%d" % len(pen["grey"]))
        shot("06-pen40.png")

        # ---- 9. 逐个点选：单独选中 k 后，亮的只能是有子弹的 {k} ----
        bad = []
        if not a.skip_each:
            for k in sorted(set(pen["lit"]) | set(pen["grey"])):
                click_cal(k)
                one = read()
                expect = {k} if k in pen["lit"] else set()
                if set(one["lit"]) != expect:
                    bad.append({"cal": k, "lit": one["lit"], "expect": sorted(expect)})
                click_cal(k)
            check("32 个口径逐个点选：只亮当前选中且有子弹的那一个",
                  not bad, json.dumps(bad[:6], ensure_ascii=False))
        else:
            print("（--skip-each：跳过逐个点选）")

        reset()
        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "default": st, "one": c1, "two": c2,
                       "cancel": c3, "show": c4, "selectedZero": c5, "reset": c6,
                       "pen40": pen, "bad": bad}, fh, ensure_ascii=False, indent=2)
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
