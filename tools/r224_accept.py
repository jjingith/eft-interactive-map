# -*- coding: utf-8 -*-
"""R224 真实浏览器验收：时间轴必须按所选区间铺满，断档处必须断开。

用户原话（2026-11-10 15:09）：
  「现在24小时 七天和30天 怎么都是一样的曲线 注意 七天和30天 如果是因为没有数据
    那也要完整显示时间轴 没数据的部分就不显示线」

根因：`drawHistoryChart` 拿 `rows[0]` / `rows[last]`（数据首尾）当时间轴两端，
7 天与 30 天返回的是同一批 86 个点，于是被拉伸成两条一模一样的线。

R225 追加（用户 2026-11-10 15:25）：「这个注释直接去掉 不需要显示」——
图下的区间 / 样本数 / 有数据时长 / 断档说明 / 口径说明全部不再渲染。

本脚本只认渲染结果：
  1. 24h / 7 天 / 30 天 三条轴，数据起点在轴上的横向位置必须依次右移；
  2. 横轴刻度首尾必须等于接口给的 `windowStart` / `windowStart + days`；
  3. 7 天 / 30 天 里那段 6 小时断档必须断开（孤立点或分段），24h 内无断档不得断；
  4. 图下不得再出现任何解释文案（元素不存在，文本也搜不到）。

用法：python tools/r224_accept.py --port 8787 --out D:/Temp/2/r224
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

ITEM = "67600929bd0a0549d70993f6"


def q(cdp, expr):
    return cdp.eval("Promise.resolve((function(){" + expr + "})())", await_promise=True)


def api_window(port, mode, item_id, days):
    url = ("http://127.0.0.1:%d/api/price-history?mode=%s&itemId=%s&days=%d"
           % (port, mode, item_id, days))
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


READ = r"""
  var host = document.querySelector('.mk-hist72');
  if (!host) { return JSON.stringify({ host: false }); }
  var svg = host.querySelector('.mk-hist-svg');
  var lines = host.querySelectorAll('.mk-hist-line');
  var box = null;
  if (lines.length) { try { box = lines[lines.length - 1].getBBox(); } catch (e) { box = null; } }
  var starts = 0;
  for (var i = 0; i < lines.length; i++) {
    var d = lines[i].getAttribute('d') || '';
    starts += (d.match(/M/g) || []).length;
  }
  // 图下解释文案历史上都是 <p class="mk-note">。只取 SVG 之外的段落文本，
  // 不要把 SVG 里的「价格走势」标题和纵轴刻度当成注释。
  var paras = host.querySelectorAll('p');
  var tailParts = [];
  for (var n = 0; n < paras.length; n++) {
    tailParts.push((paras[n].textContent || '').trim());
  }
  return JSON.stringify({
    host: true,
    tailText: tailParts.join(' | ').replace(/\s+/g, ' ').trim(),
    paraCount: paras.length,
    footCount: host.querySelectorAll('.mk-hist-foot').length,
    gapCount: host.querySelectorAll('.mk-hist-gapnote').length,
    singleCount: host.querySelectorAll('.mk-hist-single').length,
    axis: Array.prototype.map.call(host.querySelectorAll('.mk-hist-axis-x'),
      function (t) { return (t.textContent || '').trim(); }),
    lineCount: lines.length,
    moveCount: starts,
    loneDots: host.querySelectorAll('.mk-hist-dot-lone').length,
    boxLeft: box ? Math.round(box.x) : null,
    boxWidth: box ? Math.round(box.width) : null,
    hasSvg: !!svg
  });
"""


def read_state(cdp):
    raw = q(cdp, READ)
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9425)
    ap.add_argument("--out", default="D:/Temp/2/r224")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    checks, shots, states = [], [], {}

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
        q(cdp, "if (window.GWGameMode) { window.GWGameMode.set('regular', true); } return true;")
        q(cdp, "var b=document.getElementById('view-btn-market'); if(b){b.click();} return true;")
        base.wait_for(cdp, "document.querySelectorAll('tr.mk-row').length > 0",
                      timeout=90, label="行情表格")
        q(cdp, "var tr=document.querySelector('tr.mk-row');"
               "var n=tr?tr.querySelector('.mk-name'):null; if(n){n.click();} return true;")
        base.wait_for(cdp, "(function(){var h=document.querySelector('.mk-hist72');"
                          "return !!(h && h.querySelector('.mk-hist-svg'));})()",
                      timeout=90, label="历史曲线")

        for label, days in (("24h", 1), ("7 天", 7), ("30 天", 30)):
            check("点到 %s" % label, bool(click_range(cdp, label)), label)
            base.wait_for(cdp,
                          "(function(){var h=document.querySelector('.mk-hist72');"
                          "return !!(h && h.querySelector('.mk-hist-svg'));})()",
                          timeout=60, label="%s 曲线" % label)
            time.sleep(0.8)
            st = read_state(cdp)
            states[label] = st
            shot = os.path.join(a.out, "r224-%s.png" % ("24h" if days == 1 else "%dd" % days))
            shots.append(shot)
            cdp.shot(shot)

            api = api_window(a.port, "regular", ITEM, days)
            ws = api.get("windowStart")
            if ws:
                start = datetime.datetime.fromisoformat(ws)
                end = start + datetime.timedelta(days=days)
                want_start = start.strftime("%m-%d %H:%M")
                want_end = end.strftime("%m-%d %H:%M")
                axis = st.get("axis") or []
                check("%s 轴首刻度 = 区间起点" % label,
                      bool(axis) and axis[0] == want_start, "axis=%s want=%s" % (axis[:1], want_start))
                check("%s 轴末刻度 = 区间终点" % label,
                      bool(axis) and axis[-1] == want_end, "axis=%s want=%s" % (axis[-1:], want_end))
            check("%s 有 3 个横轴刻度" % label, len(st.get("axis") or []) >= 3,
                  st.get("axis"))
            # R225：图下一律没有解释文案
            check("%s 无页脚 / 断档说明 / 单点说明元素" % label,
                  (st.get("footCount") or 0) == 0 and (st.get("gapCount") or 0) == 0
                  and (st.get("singleCount") or 0) == 0,
                  "foot=%s gap=%s single=%s" % (st.get("footCount"), st.get("gapCount"),
                                                st.get("singleCount")))
            tail = st.get("tailText") or ""
            check("%s 图下一个段落都没有" % label, (st.get("paraCount") or 0) == 0,
                  "para=%s tail=%r" % (st.get("paraCount"), tail[:160]))
            for banned in ("样本", "有数据", "没有样本", "逐笔成交", "覆盖", "区间 "):
                check("%s 文本不含「%s」" % (label, banned), banned not in tail, tail[:120])

        b24, b7, b30 = states["24h"], states["7 天"], states["30 天"]
        check("7 天数据起点比 24h 更靠右",
              b7.get("boxLeft", 0) > b24.get("boxLeft", 0) + 40,
              "24h=%s 7d=%s" % (b24.get("boxLeft"), b7.get("boxLeft")))
        check("30 天数据起点比 7 天更靠右（三条轴不再重合）",
              b30.get("boxLeft", 0) > b7.get("boxLeft", 0) + 60,
              "7d=%s 30d=%s" % (b7.get("boxLeft"), b30.get("boxLeft")))
        check("30 天折线宽度明显窄于 7 天",
              (b30.get("boxWidth") or 0) < (b7.get("boxWidth") or 0),
              "7d=%s 30d=%s" % (b7.get("boxWidth"), b30.get("boxWidth")))
        check("7 天里那段 6 小时断档被断开",
              (b7.get("loneDots") or 0) >= 1 or (b7.get("lineCount") or 0) >= 2,
              "lone=%s lines=%s move=%s" % (b7.get("loneDots"), b7.get("lineCount"), b7.get("moveCount")))
        check("30 天同样断开", (b30.get("loneDots") or 0) >= 1 or (b30.get("lineCount") or 0) >= 2,
              "lone=%s lines=%s" % (b30.get("loneDots"), b30.get("lineCount")))
        check("24h 内 30 分钟连续采样不断线",
              (b24.get("lineCount") or 0) == 1 and (b24.get("loneDots") or 0) == 0,
              "lines=%s lone=%s" % (b24.get("lineCount"), b24.get("loneDots")))
        check("三档图下都没有任何段落文案",
              (b24.get("paraCount") or 0) == 0 and (b7.get("paraCount") or 0) == 0
              and (b30.get("paraCount") or 0) == 0,
              "24h=%s 7d=%s 30d=%s" % (b24.get("paraCount"), b7.get("paraCount"),
                                       b30.get("paraCount")))

        report = {"checks": checks, "shots": shots, "states": states}
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        for k in ("24h", "7 天", "30 天"):
            print("%-4s 轴=%s | 图下文本=%r" % (k, states[k].get("axis"),
                                                (states[k].get("tailText") or "")[:40]))
        return 0 if all(c["ok"] for c in checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
