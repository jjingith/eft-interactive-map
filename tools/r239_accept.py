# -*- coding: utf-8 -*-
"""R239 真实验收：透明价格浮窗（用户纠偏版）。

用户原话（2026-11-11 16:29）：
  「不对 我的需求是显示的浮窗和小地图一样 是不影响游戏操作的
    而且 应该是透明背景 只显示价格文字 然后价格文字是直接显示在对应装备上的」

覆盖：
  A. HTTP：交接态 POST/GET 往返、白名单瘦身、条数截断、非法 region 400；
  B. 浏览器：scan.html autotest 框选 → 识别 → 交接（标题「EFT截图·完成」，
     /api/ocr/overlay/state 里出现区域与匹配）；
  C. 宿主原生浮窗（--demo-overlay）：标签窗 EXSTYLE 必含
     LAYERED|TRANSPARENT|NOACTIVATE|TOOLWINDOW|TOPMOST（全窗点击穿透），
     控制条窗有 LAYERED、**无** TRANSPARENT（按钮可点），
     并截屏取证（build/_r239_overlay_demo.png：价格应叠在装备名上、背景透明）。

用法：python tools/r239_accept.py --port 8787 --out docs/r239
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME_PNG = os.path.join(ROOT, "build", "_ocr_frame_test.png")
PY314 = r"C:\Python314\python.exe"

READ = r"""
  return JSON.stringify({
    title: document.title,
    testReady: !!(window.__scanTest && window.__scanTest.ready),
    handedOff: !!(window.__scanTest && window.__scanTest.handedOff),
    matches: (window.__scanTest && window.__scanTest.matches || []).length,
    region: (window.__scanTest && window.__scanTest.region) || null
  });
"""


def read(cdp):
    raw = cdp.eval("(function(){" + READ + "})()")
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _json_req(port, path, payload=None, method=None):
    data = None
    headers = {}
    m = method
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        m = m or "POST"
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                 headers=headers, method=m)
    try:
        with _opener().open(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9437)
    ap.add_argument("--out", default="docs/r239")
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--skip-demo", action="store_true", help="跳过宿主演示（Windows 原生部分）")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    # ================= A. HTTP：交接态 =================
    st = _json_req(a.port, "/api/ocr/overlay/state")
    check("交接态端点可用（长驻 BFF 可能残留上次交接，只验响应契约）",
          st.get("ok") is True and isinstance(st.get("active"), bool)
          and isinstance(st.get("matches"), list), json.dumps(st)[:120])

    synth = {"region": {"x": 10, "y": 20, "w": 400, "h": 300},
             "matches": [{"name": "合成物品", "x": 12, "y": 24, "w": 120, "h": 18,
                          "gw": 1, "gh": 1, "weight": 0.5,
                          "price": {"lastLow": 123400}, "junk": 1}]}
    st = _json_req(a.port, "/api/ocr/overlay/state", synth)
    check("交接态写入成功", st.get("ok") and st.get("count") == 1, json.dumps(st)[:120])
    st = _json_req(a.port, "/api/ocr/overlay/state")
    m = (st.get("matches") or [{}])[0]
    check("往返一致 + 白名单瘦身（junk 被丢）",
          st.get("active") is True and m.get("name") == "合成物品" and "junk" not in m,
          json.dumps(st)[:200])
    st = _json_req(a.port, "/api/ocr/overlay/state", {"matches": []})
    check("缺 region → 400", st.get("error") is not None, json.dumps(st)[:120])

    # ================= B. 浏览器：autotest 交接 =================
    if not os.path.exists(FRAME_PNG):
        print("缺 %s（先跑 tools/r238_accept.py 或手动生成）" % FRAME_PNG)
        return 2
    with open(FRAME_PNG, "rb") as f:
        data = f.read()
    req = urllib.request.Request("http://127.0.0.1:%d/api/ocr/frame" % a.port, data=data,
                                 headers={"Content-Type": "application/octet-stream"},
                                 method="POST")
    with _opener().open(req, timeout=60) as r:
        fid = json.loads(r.read().decode("utf-8"))["id"]
    check("冻结帧上传", bool(fid), fid)

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
        url = ("http://127.0.0.1:%d/scan.html?frame=%s&mode=regular&autotest=1"
               "&bbox=30,20,560,300" % (a.port, fid))
        cdp.call("Page.navigate", url=url)
        base.wait_ready(cdp)
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.ready",
                      timeout=30, label="冻结帧加载")
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.handedOff",
                      timeout=120, label="autotest 框选→识别→交接（标题=完成）")
        st = read(cdp)
        check("交接标题「EFT截图·完成」", st["handedOff"], "title=%r" % st["title"])
        check("识别 ≥3 件", st["matches"] >= 3, "matches=%s" % st["matches"])

        got = _json_req(a.port, "/api/ocr/overlay/state")
        reg = got.get("region") or {}
        # 区域是「图像坐标」：CDP 窗口 client ≠ 帧尺寸时页面按比例换算（正确行为），
        # 所以只断言左上角对齐 + 区域不小于框选、放大不超过 1.2 倍。
        region_ok = (abs(reg.get("x", -99) - 30) <= 6 and abs(reg.get("y", -99) - 20) <= 6
                     and 560 <= reg.get("w", 0) <= 560 * 1.2
                     and 300 <= reg.get("h", 0) <= 300 * 1.2)
        check("交接区域与框选一致（图像坐标，允许显示比例换算）", region_ok, json.dumps(reg))
        names = [mm.get("name", "") for mm in got.get("matches") or []]
        for want in ("工厂紧急出口钥匙", "马卡洛夫9x18PM 手枪"):
            check("交接匹配含「%s」" % want, any(want in n for n in names), names[:4])
        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    # ================= C. 宿主原生浮窗（Windows 演示） =================
    if not a.skip_demo and sys.platform == "win32" and os.path.exists(PY314):
        r = subprocess.run(
            [PY314, os.path.join(ROOT, "tools", "scan.py"),
             "--server", "http://127.0.0.1:%d" % a.port, "--demo-overlay",
             "--demo-seconds", "6"],
            capture_output=True, text=True, timeout=300, cwd=ROOT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (r.stdout or "") + (r.stderr or "")
        result_line = next((ln for ln in out.splitlines() if ln.startswith("RESULT")), "")
        check("宿主演示运行完成（退出码 0）", r.returncode == 0,
              "rc=%s %s" % (r.returncode, out[-300:] if r.returncode else ""))
        if result_line:
            kv = dict(p.split("=", 1) for p in result_line.split()[1:])
            ex_l = int(kv.get("labels_ex", "0"), 16)
            ex_c = int(kv.get("control_ex", "0"), 16)
            WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
            WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x8000000, 0x80, 0x8
            check("标签窗全窗点击穿透样式（LAYERED|TRANSPARENT|NOACTIVATE|TOOLWINDOW|TOPMOST）",
                  (ex_l & (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                           | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)) == (
                      WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                      | WS_EX_TOOLWINDOW | WS_EX_TOPMOST),
                  result_line)
            check("控制条窗可点（有 LAYERED、无 TRANSPARENT）",
                  (ex_c & WS_EX_LAYERED) and not (ex_c & WS_EX_TRANSPARENT), result_line)
            shot = kv.get("shot", "")
            check("浮窗取证截图已生成", shot and os.path.exists(shot), shot)
            print("DEMO_SHOT=%s" % shot)

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
