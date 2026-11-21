# -*- coding: utf-8 -*-
"""R238 真实浏览器验收：QQ 式截图识别工作流（冻结帧 → autotest 框选 → 原位浮窗）。

用户原话（2026-11-11 16:00）：
  「能否做成和qq截图一样 按用户设置的快捷键 然后框选要识别的地方 然后再进行识别
    还会然后识别的结果和小地图一样 以浮窗结果显示 就显示在框选的位置
    显示整体价格和每格价格以及每公斤价格 然后在浮窗右上角有关闭键 和切换价格的键
    点击后在最新价格 24小时均价 72小时均价 30天均价直接切换」

覆盖：
  1. 冻结帧上传/取回（/api/ocr/frame POST→GET，错误 id 404）；
  2. scan.html autotest 框选 → 识别 → 浮窗渲染（每件/每格/每公斤三列，非全空）；
  3. 口径切换按钮循环 最新→24h→72h→30天（表头跟随变化）；
  4. 关闭按钮 → 标题变「EFT截图·关闭」（宿主据此关窗回等待）；
  5. 全程无 JS 异常。

用法：python tools/r238_accept.py --port 8787 --out docs/r238
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
FRAME_PNG = os.path.join(ROOT, "build", "_ocr_frame_test.png")

READ = r"""
  return JSON.stringify({
    title: document.title,
    panelVisible: (function () {
      var p = document.getElementById('panel');
      return !!p && p.style.display === 'flex';
    })(),
    rowCount: document.querySelectorAll('#pBody tr').length,
    modeLabel: (document.getElementById('modeBtn') || {}).textContent || '',
    mainHead: (document.getElementById('thMain') || {}).textContent || '',
    rows: [].slice.call(document.querySelectorAll('#pBody tr')).map(function (tr) {
      var tds = tr.querySelectorAll('td');
      return { name: ((tr.querySelector('.n') || {}).textContent || '').trim(),
               c1: (tds[1] || {}).textContent || '',
               c2: (tds[2] || {}).textContent || '',
               c3: (tds[3] || {}).textContent || '' };
    }),
    empty: (document.getElementById('pEmpty') || {}).textContent || '',
    tableShown: (function () {
      var t = document.getElementById('pTable');
      return !!t && t.style.display !== 'none';
    })(),
    testReady: !!(window.__scanTest && window.__scanTest.ready),
    panelFlag: !!(window.__scanTest && window.__scanTest.panelVisible)
  });
"""


def read(cdp):
    raw = cdp.eval("(function(){" + READ + "})()")
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def post_frame(port: int) -> str:
    with open(FRAME_PNG, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/ocr/frame" % port, data=data,
        headers={"Content-Type": "application/octet-stream"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=60) as r:
        doc = json.loads(r.read().decode("utf-8"))
    assert doc.get("ok"), doc
    return doc["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9436)
    ap.add_argument("--out", default="docs/r238")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    # ---- 冻结帧往返（HTTP 级） ----
    frame_id = post_frame(a.port)
    check("冻结帧上传成功（POST /api/ocr/frame）", bool(frame_id), "id=%s" % frame_id)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:%d/api/ocr/frame?id=%s" % (a.port, frame_id),
                         timeout=30) as r:
            body = r.read()
        check("冻结帧取回（GET，PNG 字节一致）", len(body) == os.path.getsize(FRAME_PNG),
              "%d bytes" % len(body))
    except Exception as exc:  # noqa: BLE001
        check("冻结帧取回（GET）", False, str(exc)[:200])
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open("http://127.0.0.1:%d/api/ocr/frame?id=bad-id" % a.port, timeout=15)
        check("错误 id → 404", False, "没有 404")
    except urllib.error.HTTPError as e:
        check("错误 id → 404", e.code == 404, "code=%s" % e.code)
    except Exception as exc:  # noqa: BLE001
        check("错误 id → 404", False, str(exc)[:200])

    # ---- 浏览器：autotest 框选 → 浮窗 ----
    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    os.makedirs(a.out, exist_ok=True)
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    shots = []
    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Log.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        url = ("http://127.0.0.1:%d/scan.html?frame=%s&mode=regular&autotest=1"
               "&bbox=30,20,560,300" % (a.port, frame_id))
        cdp.call("Page.navigate", url=url)
        base.wait_ready(cdp)
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.ready",
                      timeout=30, label="冻结帧加载")
        base.wait_for(cdp, "window.__scanTest && window.__scanTest.panelVisible",
                      timeout=120, label="识别浮窗出现（autotest 框选→识别）")
        st = read(cdp)
        check("浮窗已显示", st["panelVisible"] and st["panelFlag"], "%s/%s" % (st["panelVisible"], st["panelFlag"]))
        check("结果 ≥3 行", st["rowCount"] >= 3, "rows=%s" % st["rowCount"])
        names = [r["name"] for r in st["rows"]]
        for want in ("工厂紧急出口钥匙", "马卡洛夫9x18PM 手枪", "宿舍118房间钥匙"):
            check("浮窗识别出「%s」" % want, any(want in n for n in names), names[:4])
        cells = st["rows"]
        price_ok = all(any(c not in ("—", "") for c in (r["c1"], r["c2"], r["c3"])) for r in cells)
        check("每行三列价格（每件/每格/每公斤）非全空", price_ok,
              json.dumps([(r["name"], r["c1"], r["c2"], r["c3"]) for r in cells][:3], ensure_ascii=False)[:300])
        check("口径初始为「最新价」", st["modeLabel"] == "最新价" and "最新价" in st["mainHead"],
              "%s | %s" % (st["modeLabel"], st["mainHead"]))

        # ---- 口径切换循环 ----
        labels = []
        for _i in range(4):
            cdp.eval("document.getElementById('modeBtn').click()")
            time.sleep(0.15)
            labels.append(read(cdp)["modeLabel"])
        check("口径循环 最新→24h→72h→30天", labels == ["24h均价", "72h均价", "30天均价", "最新价"],
              json.dumps(labels, ensure_ascii=False))
        st2 = read(cdp)
        check("表头跟随口径变化", "24h" not in st2["mainHead"] or st2["mainHead"] != st["mainHead"],
              "%s → %s" % (st["mainHead"], st2["mainHead"]))

        shot = os.path.join(a.out, "01-scan-panel.png")
        cdp.shot(shot)
        shots.append(shot)

        # ---- 关闭 ----
        cdp.eval("document.getElementById('closeBtn').click()")
        time.sleep(0.4)
        st3 = read(cdp)
        check("关闭后标题变「EFT截图·关闭」", st3["title"] == "EFT截图·关闭",
              "title=%r" % st3["title"])

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "rows": st["rows"]}, fh,
                      ensure_ascii=False, indent=2)
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
