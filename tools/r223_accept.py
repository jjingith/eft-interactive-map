# -*- coding: utf-8 -*-
"""R223 真实浏览器验收：确认「Collected 计数」已整块消失，且没有删出空洞。

不认代码注释，只看渲染结果：
  1. 详情弹窗里不存在 `.mk-collected`，页面上也搜不到「Collected 计数」；
  2. 左列仍有价格摘要与 Sell to，且左列没有留下大块空白（高度合理）；
  3. 弹窗仍能正常打开、三个 Tab 仍能切换（删除没有牵连交互）；
  4. 浏览器控制台无报错（事件委托删干净了，不会留空引用）；
  5. 截图留证。

用法：python tools/r223_accept.py --port 8787 --out D:/Temp/2/r223
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


def q(cdp, expr):
    return cdp.eval("Promise.resolve((function(){" + expr + "})())", await_promise=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9424)
    ap.add_argument("--out", default="D:/Temp/2/r223")
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
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        # 收集控制台异常
        cdp.call("Log.enable")
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)
        q(cdp, "window.__r223errs=[];"
               "window.addEventListener('error',function(e){window.__r223errs.push(String(e.message));});"
               "return true;")
        q(cdp, "if (window.GWGameMode) { window.GWGameMode.set('regular', true); } return true;")
        q(cdp, "var b=document.getElementById('view-btn-market'); if(b){b.click();} return true;")
        base.wait_for(cdp, "document.querySelectorAll('tr.mk-row').length > 0",
                      timeout=90, label="行情表格")

        q(cdp, "var tr=document.querySelector('tr.mk-row');"
               "var n=tr?tr.querySelector('.mk-name'):null; if(n){n.click();} return true;")
        base.wait_for(cdp, "!!document.querySelector('.mk-modal-left')", timeout=30, label="详情弹窗")

        info = q(cdp, r"""
          var left = document.querySelector('.mk-modal-left');
          var body = document.querySelector('.mk-modal-body');
          var box  = document.querySelector('.mk-collected');
          return JSON.stringify({
            hasCollected: !!box,
            leftText: left ? (left.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200) : '',
            leftH: left ? Math.round(left.getBoundingClientRect().height) : 0,
            bodyH: body ? Math.round(body.getBoundingClientRect().height) : 0,
            hasPrice: !!(left && left.querySelector('.mk-priceblock')),
            hasSellto: !!(left && left.querySelector('.mk-sellto')),
            selltoRows: left ? left.querySelectorAll('.mk-sellto-row, .mk-sellto-best').length : 0,
            wholePageHasCollected: (document.body.textContent || '').indexOf('Collected 计数') >= 0,
            wholePageHasWeiji: (document.body.textContent || '').indexOf('仅保存在本机') >= 0,
            errs: window.__r223errs || []
          });
        """)
        info = json.loads(info) if isinstance(info, str) else (info or {})

        shots.append(os.path.join(a.out, "r223-modal.png"))
        cdp.shot(shots[-1])

        check("详情里没有 .mk-collected", not info.get("hasCollected"), info.get("hasCollected"))
        check("页面搜不到「Collected 计数」", not info.get("wholePageHasCollected"))
        check("页面搜不到「仅保存在本机」", not info.get("wholePageHasWeiji"))
        check("左列仍有价格摘要", info.get("hasPrice"))
        check("左列仍有 Sell to", info.get("hasSellto") and info.get("selltoRows", 0) > 0,
              "sellto 行=%s" % info.get("selltoRows"))
        check("左列没有留下大块空白", 120 <= info.get("leftH", 0) <= 520,
              "leftH=%s bodyH=%s" % (info.get("leftH"), info.get("bodyH")))
        check("左列文案里没有「未记录」", "未记录" not in (info.get("leftText") or ""),
              info.get("leftText"))

        # Tab 仍可切换
        tab_ok = q(cdp, r"""
          var btns = document.querySelectorAll('.mk-modal-tabs [data-tab]');
          if (!btns || btns.length < 3) { return false; }
          for (var i = 0; i < btns.length; i++) {
            if (btns[i].getAttribute('data-tab') === 'uses') { btns[i].click(); break; }
          }
          return true;
        """)
        time.sleep(0.4)
        used = q(cdp, r"""
          var pane = document.querySelector('.mk-tabpane');
          var sel = document.querySelector('.mk-modal-tabs [aria-selected="true"]');
          return JSON.stringify({
            tab: sel ? sel.getAttribute('data-tab') : '',
            paneLen: pane ? (pane.textContent || '').trim().length : 0
          });
        """)
        used = json.loads(used) if isinstance(used, str) else (used or {})
        check("Uses Tab 可切换且有内容", bool(tab_ok) and used.get("tab") == "uses"
              and used.get("paneLen", 0) > 0, used)
        shots.append(os.path.join(a.out, "r223-uses-tab.png"))
        cdp.shot(shots[-1])

        check("没有 JS 运行时报错", not info.get("errs"), info.get("errs"))

        report = {"checks": checks, "shots": shots, "page": info, "tab": used}
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        print("左列高度 %s px / 弹窗主体 %s px" % (info.get("leftH"), info.get("bodyH")))
        return 0 if all(c["ok"] for c in checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
