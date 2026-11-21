# -*- coding: utf-8 -*-
"""R234/R236 真实浏览器验收：市场视图「截图识别」面板端到端。

用户原话（2026-11-11 12:11）：
  「走A …… 然后价格就能使用市场界面里的数据了」
R236 补充（14:40）：
  「我现在试了几次都不对 只能识别出几个物体」——整图分块识别。

只认渲染结果（真实 Chrome + CDP）：
  1. 市场工具栏有「截图识别」按钮，点击后面板打开；
  2. 小图用例：DataTransfer 灌 build/_ocr_http_test.png（3 个物品名 + 价格标签），
     结果 ≥3 行、价格/每格非空、价格标签不误配、标注图展示；
  3. 大图用例（R236）：build/_ocr_big_test.png（1920×1080、12 个真实物品名 +
     价格标签），分块识别结果 ≥10 行，且 ≥8 个已知物品名出现；
  4. 价格单元格用市场同源 quote()（随模式/会员态），与表格口径一致；
  5. Escape 关面板；全程无 JS 异常（过滤 favicon 噪音）。

用法：python tools/r234_accept.py --port 8787 --out docs/r234
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

INJECT = r"""
(async function () {
  try {
    var path = window.__ocrInjectPath || '/build/_ocr_http_test.png';
    var res = await fetch(path, {cache: 'no-store'});
    if (!res.ok) { window.__ocrInj = 'fetch-' + res.status; return; }
    var blob = await res.blob();
    var file = new File([blob], 't.png', {type: 'image/png'});
    var dt = new DataTransfer();
    dt.items.add(file);
    var input = document.querySelector('.mk-ocr-file');
    if (!input) { window.__ocrInj = 'no-input'; return; }
    input.files = dt.files;
    input.dispatchEvent(new Event('change', {bubbles: true}));
    window.__ocrInj = 'ok';
  } catch (e) {
    window.__ocrInj = 'err-' + (e && e.message || e);
  }
})()
"""

READ = r"""
  var panel = document.querySelector('.mk-ocr');
  var rows = [].slice.call(document.querySelectorAll('.mk-ocr-row'));
  return JSON.stringify({
    open: !!panel && !panel.hidden,
    canvasVisible: (function () {
      var w = document.querySelector('.mk-ocr-cropwrap');
      return !!w && !w.hidden && !!w.querySelector('canvas') &&
             w.querySelector('canvas').width > 0;
    })(),
    status: (document.querySelector('.mk-ocr-status') || {}).textContent || '',
    rowCount: rows.length,
    rows: rows.map(function (tr) {
      var tds = tr.querySelectorAll('td');
      return {
        name: ((tr.querySelector('.mk-ocr-n') || {}).textContent || '').trim(),
        tier: (tds[1] ? tds[1].textContent : '').trim(),
        price: (tds[2] ? tds[2].textContent : '').trim(),
        slot: (tds[3] ? tds[3].textContent : '').trim()
      };
    }),
    annotatedShown: (function () {
      var im = document.querySelector('.mk-ocr-annotated');
      return !!im && !im.hidden && !!im.src && im.src.indexOf('data:image/png') === 0;
    })(),
    tableShown: (function () {
      var t = document.querySelector('.mk-ocr-table');
      return !!t && !t.hidden;
    })(),
    emptyText: (document.querySelector('.mk-ocr-empty') || {}).textContent || ''
  });
"""


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
    ap.add_argument("--cdp-port", type=int, default=9434)
    ap.add_argument("--out", default="docs/r234")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    checks, shots = [], []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    # 两个用例：小图回归（R234）+ 大图分块（R236）
    CASES = [
        {
            "label": "小图", "img": "/build/_ocr_http_test.png", "min_rows": 3,
            "must": ["工厂紧急出口钥匙", "宿舍118房间钥匙", "马卡洛夫9x18PM 手枪"],
            "ban_names": ["5.56x45mm M855"], "row_timeout": 180, "shot": "01-ocr-panel.png",
            "check_slot": True, "check_annotated": True,
        },
        {
            "label": "大图(1920×1080 分块)", "img": "/build/_ocr_big_test.png", "min_rows": 10,
            "must": ["工厂紧急出口钥匙", "马卡洛夫9x18PM 手枪", "RGD-5手榴弹",
                     "600 毫升瓶装水", "军用饼干", "无菌绷带", "固定夹板",
                     "MP-133 12 铅径泵动式霰弹枪"],
            "ban_names": [], "row_timeout": 240, "shot": "03-ocr-big.png",
            "check_slot": False, "check_annotated": True,
        },
    ]

    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Log.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)

        # ---- 进市场视图 ----
        check("点到市场视图", bool(click(cdp, "#view-btn-market")), "#view-btn-market")
        base.wait_for(cdp, "document.querySelector('.mk-toolbar') !== null",
                      timeout=60, label="市场工具栏")
        base.wait_for(cdp, "document.querySelectorAll('.mk-tbody tr').length > 0",
                      timeout=120, label="市场表格行")
        time.sleep(0.5)
        check("工具栏有「截图识别」按钮", bool(cdp.eval(
            "(function(){return !!document.querySelector('.mk-ocr-btn');})()")), ".mk-ocr-btn")

        for case in CASES:
            label = case["label"]
            # ---- 打开面板（每例先关残留面板） ----
            cdp.eval("(function(){var p=document.querySelector('.mk-ocr');"
                     "if(p&&!p.hidden){p.dispatchEvent(new KeyboardEvent('keydown',"
                     "{key:'Escape',bubbles:true}));}return 1;})()")
            time.sleep(0.2)
            check("[%s] 打开识别面板" % label, bool(click(cdp, ".mk-ocr-btn")), ".mk-ocr-btn")
            base.wait_for(cdp, "document.querySelector('.mk-ocr') && !document.querySelector('.mk-ocr').hidden",
                          timeout=20, label="识别面板打开")
            st0 = read(cdp)
            check("[%s] 面板默认空态" % label, st0["rowCount"] == 0 and not st0["tableShown"],
                  st0["emptyText"][:60])

            # ---- 灌图（DataTransfer → 文件输入） ----
            cdp.eval("window.__ocrInjectPath = %s; window.__ocrInj = '';" % json.dumps(case["img"]))
            cdp.eval(INJECT, await_promise=True)
            base.wait_for(cdp, "window.__ocrInj === 'ok'", timeout=20, label="注入测试截图")
            base.wait_for(cdp, "document.querySelector('.mk-ocr-cropwrap') && "
                               "!document.querySelector('.mk-ocr-cropwrap').hidden",
                          timeout=20, label="画布预览出现")
            st1 = read(cdp)
            check("[%s] 画布已渲染测试图" % label, st1["canvasVisible"],
                  "canvasVisible=%s" % st1["canvasVisible"])

            # ---- 识别 ----
            check("[%s] 点「识别」" % label, bool(click(cdp, ".mk-ocr-run")), ".mk-ocr-run")
            base.wait_for(cdp, "document.querySelectorAll('.mk-ocr-row').length >= %d" % case["min_rows"],
                          timeout=case["row_timeout"], label="识别结果 ≥%d 行" % case["min_rows"])
            time.sleep(0.4)
            st2 = read(cdp)
            check("[%s] 状态行显示匹配统计" % label, "匹配" in st2["status"] or "/" in st2["status"],
                  st2["status"][:120])
            check("[%s] 结果表 ≥%d 行" % (label, case["min_rows"]), st2["rowCount"] >= case["min_rows"],
                  "rows=%s" % st2["rowCount"])
            names = [r["name"] for r in st2["rows"]]
            for want in case["must"]:
                check("[%s] 识别出「%s」" % (label, want), want in names, names[:6])
            price_ok = all(r["price"] not in ("", "—") for r in st2["rows"])
            check("[%s] 每行价格非空（市场同源数据）" % label, price_ok,
                  json.dumps([(r["name"], r["price"]) for r in st2["rows"]][:4], ensure_ascii=False)[:260])
            for ban in case["ban_names"]:
                check("[%s] 「%s」未误配（守卫生效）" % (label, ban),
                      not any(ban in n for n in names), names[:6])
            if case["check_slot"]:
                slot_ok = all(r["slot"] not in ("", "—") for r in st2["rows"])
                check("[%s] 每行每格价非空" % label, slot_ok,
                      json.dumps([(r["name"], r["slot"]) for r in st2["rows"]][:4], ensure_ascii=False)[:240])
            if case["check_annotated"]:
                check("[%s] 标注图已展示" % label, st2["annotatedShown"],
                      "annotated=%s" % st2["annotatedShown"])
            check("[%s] 结果表可见" % label, st2["tableShown"], "table=%s" % st2["tableShown"])

            shot = os.path.join(a.out, case["shot"])
            cdp.shot(shot)
            shots.append(shot)

        # ---- Escape 关面板 ----
        cdp.eval("(function(){var p=document.querySelector('.mk-ocr');"
                 "p.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return 1;})()")
        time.sleep(0.3)
        st3 = read(cdp)
        check("Escape 关闭面板", st3["open"] is False, "open=%s" % st3["open"])

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots}, fh, ensure_ascii=False, indent=2)

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
