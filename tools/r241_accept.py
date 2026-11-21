# -*- coding: utf-8 -*-
"""R241 浏览器验收：价格识别设置面板（菜单栏小地图按钮右侧）。

覆盖：
  A. HTTP：/api/config 带 ocrScan 默认值（4 档 + 热键）；
  B. 浏览器：点「价格识别」按钮 → 面板打开 → 默认 4 个档位行 → 热键可编辑 →
     改热键为 f8 → ≤5s 内 /api/config 回声 hotkey=f8（并验证宿主日志热切换）；
     会员锁状态与 isMember() 一致；无 JS 异常；
  C. 收尾：把热键改回 ctrl+alt+p（不污染用户配置），宿主日志确认切回。

用法：python tools/r241_accept.py --port 8787 --out docs/r241
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST_LOG = os.path.join(ROOT, "build", "scan-host.log")


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _json_req(port, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                 headers={"Content-Type": "application/json"} if data else {},
                                 method="POST" if data else "GET")
    try:
        with _opener().open(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def host_log_tail(n=600):
    try:
        with open(HOST_LOG, encoding="utf-8") as f:
            return f.read()[-n:]
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9439)
    ap.add_argument("--out", default="docs/r241")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    # ---- A. HTTP：配置默认值 ----
    cfg = _json_req(a.port, "/api/config").get("config") or {}
    ocr = cfg.get("ocrScan") or {}
    tiers = (ocr.get("labelStyle") or {}).get("tiers") or []
    check("配置含 ocrScan 默认值（热键 + 4 档）",
          ocr.get("hotkey") == "ctrl+alt+p" and len(tiers) == 4
          and tiers[-1].get("max") is None, json.dumps(ocr)[:200])

    # ---- B. 浏览器 ----
    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    os.makedirs(profile, exist_ok=True)
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Log.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)
        base.wait_for(cdp, "document.getElementById('am-ocr') !== null",
                      timeout=30, label="菜单栏加载（价格识别按钮）")
        cdp.eval("document.getElementById('am-ocr').click()")
        time.sleep(0.3)
        st = json.loads(cdp.eval(r"""
          (function () {
            var panel = document.getElementById('am-ocr-panel');
            var box = document.getElementById('ocr-style-box');
            var rows = document.querySelectorAll('#ocr-tiers .ocr-tier-row');
            return JSON.stringify({
              panelOpen: !!panel && !panel.hidden,
              rows: rows.length,
              hotkeyEditable: (function () {
                var i = document.getElementById('ocr-hotkey');
                return !!i && !i.disabled;
              })(),
              locked: !!box && box.classList.contains('is-member-locked'),
              styleInputsDisabled: (function () {
                var n = box ? box.querySelector('input, select, button') : null;
                return n ? n.disabled : null;
              })()
            });
          })()
        """))
        check("「价格识别」面板打开", st.get("panelOpen") is True, json.dumps(st))
        check("默认 4 个档位行渲染", st.get("rows") == 4, "rows=%s" % st.get("rows"))
        check("截图热键可编辑（免费用户也能改）", st.get("hotkeyEditable") is True)
        # 会员真值取服务端 /api/config 的 account.member（页面 isMember 在 IIFE 内，eval 不可达）
        member_truth = (cfg.get("account") or {}).get("member") is True
        check("会员锁状态与登录态一致",
              st.get("locked") == (not member_truth)
              and st.get("styleInputsDisabled") == (not member_truth),
              "member=%s locked=%s disabled=%s"
              % (member_truth, st.get("locked"), st.get("styleInputsDisabled")))

        # 改热键 → 400ms 防抖 → POST → 服务端广播回声
        cdp.eval(r"""
          (function () {
            var i = document.getElementById('ocr-hotkey');
            i.value = 'f8';
            i.dispatchEvent(new Event('change', {bubbles: true}));
          })()
        """)
        deadline = time.time() + 6
        got = ""
        while time.time() < deadline:
            cfg2 = (_json_req(a.port, "/api/config").get("config") or {}).get("ocrScan") or {}
            got = cfg2.get("hotkey") or ""
            if got == "f8":
                break
            time.sleep(0.3)
        check("热键保存生效（配置回声 f8）", got == "f8", "hotkey=%r" % got)
        # 宿主热切换（≤1.5s 轮询）
        deadline = time.time() + 4
        switched = "热键已切换为 f8" in host_log_tail(1200)
        while time.time() < deadline and not switched:
            time.sleep(0.3)
            switched = "热键已切换为 f8" in host_log_tail(1200)
        check("宿主热键热切换（日志确认，无需重启）", switched, host_log_tail()[-200:])

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    # ---- C. 收尾：热键还原 ctrl+alt+p，宿主日志确认切回 ----
    _json_req(a.port, "/api/prefs", {"ocrScan": {"hotkey": "ctrl+alt+p"}})
    deadline = time.time() + 5
    restored = False
    while time.time() < deadline and not restored:
        time.sleep(0.3)
        restored = "热键已切换为 ctrl+alt+p" in host_log_tail(1500)
    cfg = (_json_req(a.port, "/api/config").get("config") or {}).get("ocrScan") or {}
    check("热键还原为 ctrl+alt+p（配置+宿主日志）",
          cfg.get("hotkey") == "ctrl+alt+p" and restored,
          "cfg=%s restored=%s" % (cfg.get("hotkey"), restored))

    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"checks": checks}, fh, ensure_ascii=False, indent=2)
    for c in checks:
        print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                               ("  → " + c["detail"]) if c["detail"] else ""))
    ok = sum(1 for c in checks if c["ok"])
    print("\n%d/%d PASS" % (ok, len(checks)))
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
