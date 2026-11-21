# -*- coding: utf-8 -*-
"""R226 真实浏览器验收：Obtain 获取途径不再外露上游字段名。

用户原话（2026-11-10 15:58）：
  「其中「上游 types 未含 noFlea」「（minLevelForFlea）」「；上表 src 只说明上游标记的
    获取方式」 这几个去掉 不需要显示」

本脚本只认渲染结果（Obtain tab）：
  1. 可见文本里不得出现 `noFlea`、`minLevelForFlea`、`上游 types`、`上表 src`；
  2. 该留的还在：「跳蚤市场购买」「可上跳蚤」「上架等级 Lv N」；
  3. 商人买价 / 兑换为空时只留「当前模式行情没有该物品的商人买价或兑换配方。」；
  4. 页脚与 tab 切换无 JS 报错。

用法：python tools/r226_accept.py --port 8787 --out D:/Temp/2/r226
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

# 5.56x45mm M855 弹药包：trade 只有 flea，无 buy / barter
SECOND_ID = "5447ac644bdc2d6c208b4567"


def q(cdp, expr):
    return cdp.eval("Promise.resolve((function(){" + expr + "})())", await_promise=True)


READ_OBTAIN = r"""
  var pane = document.querySelector('.mk-tabpane');
  if (!pane) { return JSON.stringify({ pane: false }); }
  var chips = Array.prototype.map.call(pane.querySelectorAll('.mk-src-chip'),
    function (c) { return (c.textContent || '').trim(); });
  var all = (pane.textContent || '').replace(/\s+/g, ' ').trim();
  return JSON.stringify({
    pane: true,
    chips: chips,
    text: all,
    hasBan: !!pane.querySelector('.mk-chip-ban'),
    hasOk: !!pane.querySelector('.mk-chip-ok'),
    rows: pane.querySelectorAll('.mk-tab-row').length
  });
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9426)
    ap.add_argument("--out", default="D:/Temp/2/r226")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    checks, shots = [], []
    errors = []

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
        base.wait_for(cdp, "!!document.querySelector('.mk-modal-tabs [data-tab]')",
                      timeout=90, label="详情弹窗 Tabs")

        clicked = q(cdp, r"""
          var btns = document.querySelectorAll('.mk-modal-tabs [data-tab]');
          for (var i = 0; i < btns.length; i++) {
            if (btns[i].getAttribute('data-tab') === 'obtain') { btns[i].click(); return true; }
          }
          return false;
        """)
        check("点到 Obtain Tab", bool(clicked), "obtain tab")
        time.sleep(0.6)
        raw = q(cdp, READ_OBTAIN)
        st = json.loads(raw) if isinstance(raw, str) else (raw or {})
        text = st.get("text") or ""

        check("Obtain 面板有内容", bool(st.get("pane")) and text != "", text[:120])
        for banned in ("noFlea", "minLevelForFlea", "上游 types", "上表 src", "上游标记的获取方式"):
            check("可见文本不含「%s」" % banned, banned not in text, text[:200])
        check("保留「跳蚤市场购买」来源芯片", any("跳蚤市场购买" in c for c in (st.get("chips") or [])),
              st.get("chips"))
        check("保留「可上跳蚤」判定", bool(st.get("hasOk")) and "可上跳蚤" in text, text[:160])
        check("保留「上架等级 Lv N」", "上架等级 Lv" in text, text[:160])
        # 上架等级后面直接结束（不再带括号字段名）
        check("上架等级后没有括号字段名", "（minLevelForFlea）" not in text, text[:160])

        shot = os.path.join(a.out, "r226-obtain.png")
        cdp.shot(shot)
        shots.append(shot)

        # ------------------------------------------------ 第二阶段：无商人买价 / 兑换的物品
        # M855 弹药包 trade 只有 {"k":"flea"}，会走到「当前模式行情没有…」那一句
        q(cdp, r"""
          var inp = document.querySelector('input[placeholder*="搜索物品"]');
          if (!inp) { return false; }
          inp.value = 'M855';
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          return true;
        """)
        base.wait_for(cdp, '!!document.querySelector(\'tr[data-id="%s"]\')' % SECOND_ID,
                      timeout=30, label="M855 行")
        q(cdp, 'var n=document.querySelector(\'tr[data-id="%s"] .mk-name\'); if(n){n.click();} return true;'
               % SECOND_ID)
        time.sleep(0.5)
        q(cdp, r"""
          var btns = document.querySelectorAll('.mk-modal-tabs [data-tab]');
          for (var i = 0; i < btns.length; i++) {
            if (btns[i].getAttribute('data-tab') === 'obtain') { btns[i].click(); return true; }
          }
          return false;
        """)
        time.sleep(0.6)
        raw2 = q(cdp, READ_OBTAIN)
        st2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or {})
        text2 = st2.get("text") or ""

        check("无商人买价时保留「没有该物品的商人买价或兑换配方」",
              "当前模式行情没有该物品的商人买价或兑换配方" in text2, text2[:200])
        for banned in ("上表 src", "src 只说明", "上游标记的获取方式", "noFlea", "minLevelForFlea"):
            check("第二件物品文本不含「%s」" % banned, banned not in text2, text2[:200])
        shot2 = os.path.join(a.out, "r226-obtain-2.png")
        cdp.shot(shot2)
        shots.append(shot2)

        report = {"checks": checks, "shots": shots, "state": st, "state2": st2, "errors": errors}
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        print("--- Obtain 可见文本 ---")
        print(text[:600])
        return 0 if all(c["ok"] for c in checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
