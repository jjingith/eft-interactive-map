# -*- coding: utf-8 -*-
"""R240 真实验收：QQ 式速度（保温窗口 + BMP 冻结帧 + 轮询换帧）。

用户反馈（2026-11-11 17:11）：
  「现在按截图键 没有qq截图那样快 而且窗口什么都会动一下」

覆盖：
  A. HTTP：BMP 帧上传/取回（Content-Type image/bmp）、元信息端点（页面轮询源）、
     PNG 兼容；交接态带 ts（宿主防竞态依据）。
  B. 浏览器（关键）：scan.html **不带 frame 参数**打开 → 轮询自动拉帧（测延迟）
     → autotest 框选识别交接；随后**同一页面**再投第二帧 → 页面不重载直接进入
     第二轮框选识别交接（用 JS 标记证明无 reload——这正是宿主保温窗口的页面侧
     语义），第二轮为 BMP 真图。
  C. 宿主侧保温/屏幕外入场由 tests/test_r240_warm_scan.py 契约覆盖；
     真实热键手感由用户实测。

用法：python tools/r240_accept.py --port 8787 --out docs/r240
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
    region: (window.__scanTest && window.__scanTest.region) || null,
    frameId: (window.__scanTest && window.__scanTest.frameId) || null,
    warmMark: !!window.__scanTestWarm,
    url: location.pathname
  });
"""


def read(cdp):
    raw = cdp.eval("(function(){" + READ + "})()")
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _json_req(port, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                 headers={"Content-Type": "application/json"} if data else {},
                                 method="POST" if data else "GET")
    try:
        with _opener().open(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def _post_file(port, path: str):
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request("http://127.0.0.1:%d/api/ocr/frame" % port, data=data,
                                 headers={"Content-Type": "application/octet-stream"},
                                 method="POST")
    with _opener().open(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def make_bmp_frames(out_dir: str) -> list[str]:
    """用服务端 Python（带 PIL）把既有测试图转成两张不同的 BMP。"""
    script = (
        "from PIL import Image, ImageEnhance\n"
        "import sys\n"
        "src = r'%s'\n"
        "im = Image.open(src).convert('RGB')\n"
        "im.save(r'%s')\n"
        "ImageEnhance.Brightness(im).enhance(1.25).save(r'%s')\n"
        "print('ok')\n"
    ) % (FRAME_PNG, os.path.join(out_dir, "_r240_f1.bmp"),
         os.path.join(out_dir, "_r240_f2.bmp"))
    r = subprocess.run([PY314, "-c", script], capture_output=True, text=True,
                       timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    paths = [os.path.join(out_dir, "_r240_f1.bmp"), os.path.join(out_dir, "_r240_f2.bmp")]
    if r.returncode == 0 and all(os.path.exists(p) for p in paths):
        return paths
    print("BMP 生成失败（缺 PIL？），浏览器轮改用 PNG：%s" % (r.stderr or "")[-160:])
    return [FRAME_PNG, FRAME_PNG]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9438)
    ap.add_argument("--out", default="docs/r240")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    # ---- A. HTTP ----
    f1, f2 = make_bmp_frames(os.path.join(ROOT, "build"))
    doc = _post_file(a.port, f1)
    fid1 = doc.get("id")
    check("BMP 帧上传", bool(fid1), json.dumps(doc)[:120])
    if fid1:
        with _opener().open("http://127.0.0.1:%d/api/ocr/frame?id=%s" % (a.port, fid1),
                            timeout=30) as r:
            ct = r.headers.get("Content-Type", "")
            body = r.read()
        check("BMP 取回 Content-Type=image/bmp 且字节一致",
              ct == "image/bmp" and body == open(f1, "rb").read(), "ct=%s len=%d" % (ct, len(body)))
    meta = _json_req(a.port, "/api/ocr/frame")
    check("元信息端点（页面轮询源）", meta.get("ok") is True and bool(meta.get("id")),
          json.dumps(meta)[:120])
    st = _json_req(a.port, "/api/ocr/overlay/state",
                   {"region": {"x": 1, "y": 2, "w": 30, "h": 40}, "matches": []})
    st = _json_req(a.port, "/api/ocr/overlay/state")
    check("交接态带 ts（宿主防竞态）", isinstance(st.get("ts"), float) and st["ts"] > 0,
          json.dumps({k: st.get(k) for k in ("ok", "ts")})[:120])

    # ---- B. 浏览器：轮询拉帧 + 同页两轮（保温语义） ----
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
        # 第一轮：不带 frame 参数 → 页面轮询自动拉帧
        t0 = time.time()
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/scan.html?mode=regular&autotest=1"
                                      "&bbox=30,20,560,300" % a.port)
        base.wait_ready(cdp)
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.ready",
                      timeout=30, label="轮询拉帧→框选就绪")
        pickup_ms = (time.time() - t0) * 1000
        check("页面自动轮询拉帧（无 frame 参数）", True, "首帧就绪 %.0f ms" % pickup_ms)
        check("首帧就绪 < 5s（轮询 150ms 档）", pickup_ms < 5000, "%.0f ms" % pickup_ms)
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.handedOff",
                      timeout=120, label="第一轮 autotest 框选→识别→交接")
        st1 = read(cdp)
        got1 = _json_req(a.port, "/api/ocr/overlay/state")
        ts1 = got1.get("ts") or 0
        # 注意：交接后页面 resetIdle 会清空页面侧 matches——以 BFF 交接态为准
        check("第一轮交接完成（≥3 件）", st1["handedOff"] and len(got1.get("matches") or []) >= 3,
              "stateMatches=%s" % len(got1.get("matches") or []))
        cdp.eval("window.__scanTestWarm = true")     # 同页标记（reload 即丢失）

        # 第二轮：同一页面再投 BMP 帧 → 不重载直接进入第二轮
        doc2 = _post_file(a.port, f2)
        fid2 = doc2.get("id")
        t1 = time.time()
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.frameId === '%s'"
                      % fid2, timeout=10, label="轮询发现新帧")
        swap_ms = (time.time() - t1) * 1000
        check("同页轮询发现新帧（不重载）", True, "换帧延迟 %.0f ms" % swap_ms)
        check("换帧延迟 < 3s（可见页 150ms 档）", swap_ms < 3000, "%.0f ms" % swap_ms)
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.handedOff",
                      timeout=120, label="第二轮框选→识别→交接（保温复用）")
        st2 = read(cdp)
        got2 = _json_req(a.port, "/api/ocr/overlay/state")
        ts2 = got2.get("ts") or 0
        check("第二轮交接完成（保温复用同页 + 新交接）",
              st2["handedOff"] and st2["warmMark"] and len(got2.get("matches") or []) >= 3
              and ts2 > ts1,
              "warmMark=%s stateMatches=%s ts2>ts1=%s"
              % (st2["warmMark"], len(got2.get("matches") or []), ts2 > ts1))
        got = _json_req(a.port, "/api/ocr/overlay/state")
        reg = got.get("region") or {}
        region_ok = (abs(reg.get("x", -99) - 30) <= 6 and abs(reg.get("y", -99) - 20) <= 6
                     and 560 <= reg.get("w", 0) <= 560 * 1.25
                     and 300 <= reg.get("h", 0) <= 300 * 1.25)
        check("交接区域仍与框选一致（图像坐标）", region_ok, json.dumps(reg))
        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

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
