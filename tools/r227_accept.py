# -*- coding: utf-8 -*-
"""R227 真实浏览器验收：弹药侧栏底部那段说明不再显示。

用户原话（2026-11-10 16:45）：
  「弹药界面的这个也不要显示 隐藏掉「共 200 件弹药 / 31 种口径。价格口径 lastPrice，
    来源 实时不可用，已回退快照（PvP）；C1–C6 为对 1–6 级护甲的穿透概率（公开公式计算）。
    弹道曲线为本地 G1 阻力仿真，非线上行情。」」

本脚本只认渲染结果：
  1. `#am-note` 在默认态 / 恢复筛选后必须 hidden，且高度为 0（不能留空隙）；
  2. 侧栏文本里不得再出现「种口径」「G1 阻力仿真」「C1–C6」「弹道曲线」；
  3. `#am-hint` / `#am-count` 仍在（来源与件数没有一起消失）；
  4. 两种边界提示仍要出得来：avg7d 整列为 —、CRAFT 结果为空；
  5. 全程无 JS 异常。

用法：python tools/r227_accept.py --port 8787 --out D:/Temp/2/r227
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


READ = r"""
  var host = document.getElementById('am-note');
  var side = document.querySelector('.am-side');
  var box = host ? host.getBoundingClientRect() : null;
  var hint = document.getElementById('am-hint');
  var count = document.getElementById('am-count');
  return JSON.stringify({
    exists: !!host,
    hiddenAttr: host ? host.hasAttribute('hidden') : null,
    hiddenProp: host ? !!host.hidden : null,
    text: host ? (host.textContent || '').trim() : null,
    html: host ? (host.innerHTML || '').trim() : null,
    h: box ? Math.round(box.height) : null,
    visible: host ? !!host.offsetParent : null,
    sideText: side ? (side.textContent || '').replace(/\s+/g, ' ').trim() : '',
    hint: hint ? (hint.textContent || '').trim() : '',
    hintTitle: hint ? (hint.title || '').trim() : '',
    count: count ? (count.textContent || '').trim() : '',
    rows: document.querySelectorAll('#am-table .tbl-row').length,
    empty: (function () {
      var e = document.querySelector('#am-table .tbl-empty');
      return e ? (e.textContent || '').trim() : '';
    })()
  });
"""

BANNED = ("种口径", "G1 阻力仿真", "C1–C6", "弹道曲线", "件弹药 /", "价格口径 lastPrice")


def read(cdp):
    raw = cdp.eval("(function(){" + READ + "})()")
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def click(cdp, selector):
    return cdp.eval(
        "(function(){var e=document.querySelector(%s);if(!e){return false;}e.click();return true;})()"
        % json.dumps(selector))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9427)
    ap.add_argument("--out", default="D:/Temp/2/r227")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    checks, shots = [], []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Log.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)

        check("点到弹药视图", bool(click(cdp, "#view-btn-ammo")), "#view-btn-ammo")
        base.wait_for(cdp, "document.querySelectorAll('#am-table .tbl-row').length > 0",
                      timeout=90, label="弹药表格")
        time.sleep(0.6)

        st = read(cdp)
        check("#am-note 仍在 DOM（不是把元素删掉导致布局错位）", bool(st.get("exists")), st.get("exists"))
        check("默认态 #am-note 隐藏", st.get("hiddenProp") is True and st.get("visible") is False,
              "hidden=%s visible=%s" % (st.get("hiddenProp"), st.get("visible")))
        check("默认态 #am-note 高度为 0（不留 11px 空隙）", (st.get("h") or 0) == 0, "h=%s" % st.get("h"))
        check("默认态 #am-note 没有文字", (st.get("text") or "") == "" and (st.get("html") or "") == "",
              repr(st.get("html"))[:160])
        for banned in BANNED:
            check("侧栏文本不含「%s」" % banned, banned not in (st.get("sideText") or ""),
                  (st.get("sideText") or "")[:220])
        check("件数仍在（#am-count）", "件" in (st.get("count") or ""), st.get("count"))
        check("来源仍在（#am-hint）", bool(st.get("hint")), st.get("hint"))
        check("来源 detail 仍可悬浮查看", bool(st.get("hintTitle")), (st.get("hintTitle") or "")[:120])
        check("弹药行已渲染", (st.get("rows") or 0) > 50, "rows=%s" % st.get("rows"))

        shot1 = os.path.join(a.out, "r227-ammo.png")
        cdp.shot(shot1)
        shots.append(shot1)

        # ------------------------------------------------ 边界一：avg7d 整列为 —
        check("点到 avg7d", bool(click(cdp, '#am-price-mode [data-amprice="avg7d"]')), "avg7d")
        base.wait_for(cdp, "!document.getElementById('am-note').hidden",
                      timeout=30, label="avg7d 提示出现")
        time.sleep(0.35)
        st7 = read(cdp)
        check("avg7d 提示可见", st7.get("visible") is True and (st7.get("h") or 0) > 0,
              "h=%s" % st7.get("h"))
        check("avg7d 提示说的是价格口径", "avg7d" in (st7.get("text") or ""), st7.get("text"))
        check("avg7d 提示里没有那段旧说明",
              "种口径" not in (st7.get("text") or "") and "G1" not in (st7.get("text") or ""),
              st7.get("text"))
        shot2 = os.path.join(a.out, "r227-avg7d.png")
        cdp.shot(shot2)
        shots.append(shot2)

        # 回到 lastPrice：提示必须重新隐藏
        check("切回 lastPrice", bool(click(cdp, '#am-price-mode [data-amprice="last"]')), "last")
        base.wait_for(cdp, "document.getElementById('am-note').hidden",
                      timeout=30, label="lastPrice 提示隐藏")
        st_back = read(cdp)
        check("切回后 #am-note 再次隐藏且高度 0",
              st_back.get("hiddenProp") is True and (st_back.get("h") or 0) == 0,
              "hidden=%s h=%s" % (st_back.get("hiddenProp"), st_back.get("h")))

        # ------------------------------------------------ 边界二：CRAFT 结果为空
        check("点到 CRAFT", bool(click(cdp, '#am-source [data-amsrc="craft"]')), "craft")
        base.wait_for(cdp, "!document.getElementById('am-note').hidden",
                      timeout=30, label="CRAFT 提示出现")
        time.sleep(0.35)
        stc = read(cdp)
        check("CRAFT 提示可见", stc.get("visible") is True, "visible=%s" % stc.get("visible"))
        check("CRAFT 提示说明结果为空", "CRAFT" in (stc.get("text") or ""), stc.get("text"))
        check("CRAFT 下表格确实为空", "没有匹配" in (stc.get("empty") or ""), stc.get("empty"))
        shot3 = os.path.join(a.out, "r227-craft.png")
        cdp.shot(shot3)
        shots.append(shot3)

        # RESET 之后回到干净态
        check("点 RESET", bool(click(cdp, "#am-reset")), "#am-reset")
        base.wait_for(cdp, "document.getElementById('am-note').hidden",
                      timeout=30, label="RESET 后提示隐藏")
        base.wait_for(cdp, "document.querySelectorAll('#am-table .tbl-row').length > 50",
                      timeout=90, label="RESET 后表格恢复")
        st_final = read(cdp)
        check("RESET 后 #am-note 隐藏且高度 0",
              st_final.get("hiddenProp") is True and (st_final.get("h") or 0) == 0,
              "hidden=%s h=%s" % (st_final.get("hiddenProp"), st_final.get("h")))
        for banned in BANNED:
            check("RESET 后侧栏仍不含「%s」" % banned, banned not in (st_final.get("sideText") or ""),
                  (st_final.get("sideText") or "")[:220])

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        # 只关心本轮相关：过滤掉 favicon / 网络 404 噪音
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        report = {"checks": checks, "shots": shots,
                  "state": st, "avg7d": st7, "craft": stc, "final": st_final}
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        print("\n默认态：side=%s" % (st.get("sideText") or "")[:180])
        print("avg7d  ：%s" % (st7.get("text") or "")[:180])
        print("CRAFT  ：%s" % (stc.get("text") or "")[:180])
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
