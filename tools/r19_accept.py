# -*- coding: utf-8 -*-
"""R19 配枪工作台真实浏览器验收（CDP）。

覆盖：选枪→默认装配→改配件→属性实时变化→恢复默认→对比表→装配预设面板。
两种窗口尺寸：1920×1080 / 1264×705。

用法：
    python tools/r19_accept.py --port 8787 --out docs/r19-gun-builder/screenshots
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 代表性枪械：步枪 / 冲锋枪 / 精确射手 / 狙击 / 霰弹 / 手枪
CASES = [
    ("AK-74 5.45x39 突击步枪", "步枪"),
    ("HK MP5 9x19", "冲锋枪"),
    ("德拉贡诺夫 SVDS", "精确射手/狙击"),
    ("柯尔特 M4A1", "步枪"),
    ("Glock 17 9x19", "手枪"),
    ("雷明顿 Model 870", "霰弹枪"),
]

JS_PICK_GUN = r"""
(function (name) {
  var i = document.getElementById('gw-search');
  if (!i) { return 'no-input'; }
  i.value = name;
  i.dispatchEvent(new Event('input', {bubbles: true}));
  i.dispatchEvent(new Event('focus'));
  var box = document.getElementById('gw-results');
  if (!box) { return 'no-box'; }
  var rows = box.querySelectorAll('button.gw-result');
  for (var k = 0; k < rows.length; k++) {
    var t = (rows[k].textContent || '').trim();
    if (t.indexOf(name) === 0 || t.indexOf(name) >= 0) {
      rows[k].click();
      return t.slice(0, 44);
    }
  }
  return 'no-match:' + rows.length;
})
"""

JS_STATS = r"""
(function () {
  var host = document.getElementById('gw-stats');
  if (!host) { return null; }
  var out = { rows: [], cost: '', parts: '', slots: '' };
  host.querySelectorAll('.gw-stat').forEach(function (r) {
    var lab = r.querySelector('.gw-stat-lab');
    var val = r.querySelector('.gw-stat-val') || r.querySelector('.gw-stat-num');
    var conf = r.querySelector('.gw-stat-conf');
    var d = r.querySelector('.gw-stat-delta');
    out.rows.push({
      label: lab ? lab.textContent.trim() : '',
      value: val ? val.textContent.trim() : '',
      conf: conf ? conf.textContent.trim() : '',
      delta: d ? d.textContent.trim() : ''
    });
  });
  return JSON.stringify(out);
})()
"""

JS_PICK_SLOT_AND_MOD = r"""
(function () {
  // 1) 在左侧槽位树里找一个还没装东西、且候选 >= 2 的槽位
  var tree = document.getElementById('gw-tree');
  if (!tree) { return JSON.stringify({ok: false, why: 'no-tree'}); }
  var nodes = tree.querySelectorAll('button, [role=button], .gw-node');
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    el.click();
    var tbl = document.getElementById('gw-table');
    var rows = tbl ? tbl.querySelectorAll('.tbl-row') : [];
    if (rows.length >= 1) {
      // 2) 选一个当前未安装的候选（aria-selected=false 的行）
      var target = null;
      for (var j = 0; j < rows.length; j++) {
        if (rows[j].getAttribute('aria-selected') !== 'true') { target = rows[j]; break; }
      }
      if (target) {
        var nm = target.querySelector('.tbl-cell[data-key=n]');
        target.click();
        return JSON.stringify({ok: true, slot: (el.textContent || '').trim().slice(0, 28),
                               mod: nm ? nm.textContent.trim().slice(0, 40) : '',
                               rows: rows.length});
      }
    }
  }
  return JSON.stringify({ok: false, why: 'no-candidate'});
})()
"""

JS_COMPARE = r"""
(function () {
  var p = document.getElementById('gw-cmp');
  if (!p || p.hidden) { return JSON.stringify({on: false}); }
  var rows = [];
  p.querySelectorAll('.gw-cmp-table tbody tr').forEach(function (tr) {
    var td = tr.querySelectorAll('td');
    if (td.length >= 4) {
      rows.push({label: td[0].textContent.trim(), base: td[1].textContent.trim(),
                 cur: td[2].textContent.trim(), delta: td[3].textContent.trim()});
    }
  });
  return JSON.stringify({on: true, n: rows.length, rows: rows});
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r19-gun-builder", "screenshots"))
    ap.add_argument("--cdp-port", type=int, default=9390)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rep = {"round": "R19", "cases": [], "shots": [], "console": [], "external": [], "layout": {}}
    shots = []

    def shot(cdp, name, full=True):
        p = os.path.join(a.out, name)
        cdp.shot(p)
        shots.append(name)
        return p

    proc = None
    try:
        proc, ws = launch(find_chrome(), a.cdp_port, 1920, 1080,
                          os.path.join(os.environ.get("TEMP", "."), "r19a-%d" % os.getpid()))
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)

        for (w, h, tag) in ((1920, 1080, "1920"), (1264, 705, "1264")):
            cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                     deviceScaleFactor=1, mobile=False)
            cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % a.port)
            wait_ready(cdp, want_url="index.html")
            cdp.eval("try{localStorage.clear()}catch(e){}")
            cdp.call("Page.reload")
            wait_ready(cdp, want_url="index.html")
            time.sleep(1.6)
            cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
            time.sleep(3.2)

            vp = {"size": tag, "build": cdp.eval(
                "(function(){var out=null;Array.prototype.forEach.call("
                "document.querySelectorAll('script'),function(s){var v=s.getAttribute('src')||'';"
                "if(v.indexOf('app.js')>=0){out=v;}});return out;})()"),
                "cases": []}

            for (idx, (name, kind)) in enumerate(CASES):
                picked = cdp.eval(JS_PICK_GUN + "(%s)" % json.dumps(name))
                if not picked or str(picked).startswith("no-"):
                    vp["cases"].append({"gun": name, "kind": kind, "error": picked})
                    continue
                time.sleep(2.4)
                base = json.loads(cdp.eval(JS_STATS) or "{}")

                # 改一个配件
                mod = json.loads(cdp.eval(JS_PICK_SLOT_AND_MOD) or "{}")
                time.sleep(1.6)
                after = json.loads(cdp.eval(JS_STATS) or "{}")

                # 恢复默认
                cdp.eval("document.getElementById('gw-default').click()")
                time.sleep(1.8)
                reset = json.loads(cdp.eval(JS_STATS) or "{}")

                def field(rows, label):
                    for r in rows:
                        if r["label"] == label:
                            return r["value"]
                    return None

                ergo_b = field(base.get("rows", []), "人机工效")
                ergo_a = field(after.get("rows", []), "人机工效")
                ergo_r = field(reset.get("rows", []), "人机工效")
                rv_b = field(base.get("rows", []), "垂直后坐力")
                rv_a = field(after.get("rows", []), "垂直后坐力")
                rv_r = field(reset.get("rows", []), "垂直后坐力")

                vp["cases"].append({
                    "gun": name, "kind": kind, "picked": picked,
                    "base": {"ergo": ergo_b, "recoilV": rv_b,
                             "parts": field(base.get("rows", []), "已装配件"),
                             "slots": field(base.get("rows", []), "改装槽位")},
                    "modified": mod,
                    "afterMod": {"ergo": ergo_a, "recoilV": rv_a,
                                 "parts": field(after.get("rows", []), "已装配件")},
                    "afterReset": {"ergo": ergo_r, "recoilV": rv_r,
                                   "parts": field(reset.get("rows", []), "已装配件")},
                    "changed": (ergo_b != ergo_a or rv_b != rv_a),
                    "resetMatches": (ergo_b == ergo_r and rv_b == rv_r),
                })
                if idx == 0:
                    shot(cdp, "%s-01-gun-default.png" % tag)

            # 对比表
            cdp.eval("document.getElementById('gw-compare').click()")
            time.sleep(1.4)
            cmpInfo = json.loads(cdp.eval(JS_COMPARE) or "{}")
            vp["compare"] = {"n": cmpInfo.get("n", 0),
                             "sample": (cmpInfo.get("rows") or [])[:4]}
            shot(cdp, "%s-02-compare.png" % tag)

            # 装配预设面板
            cdp.eval("document.getElementById('gw-build').click()")
            time.sleep(1.2)
            panel = cdp.eval("""
              (function(){
                var p=document.getElementById('gb-panel');
                if(!p){return JSON.stringify({open:false});}
                return JSON.stringify({open:true,
                  head:(p.querySelector('.gb-panel-head')||{}).textContent,
                  hasName:!!p.querySelector('.gb-panel-name'),
                  hasFile:!!p.querySelector('input[type=file]'),
                  buttons:Array.prototype.map.call(p.querySelectorAll('button'),function(b){return b.textContent.trim();})});
              })()""")
            vp["buildPanel"] = json.loads(panel or "{}")
            shot(cdp, "%s-03-build-panel.png" % tag)
            cdp.eval("(function(){var p=document.getElementById('gb-panel');if(p)p.remove();})()")

            vp["layout"] = {
                "noHScroll": cdp.eval("document.documentElement.scrollWidth <= "
                                      "document.documentElement.clientWidth + 1"),
                "clientW": cdp.eval("document.documentElement.clientWidth"),
            }
            rep["cases"].append(vp)

        rep["console"] = cdp.console
        rep["external"] = [r["url"] for r in cdp.requests
                           if not r["url"].startswith("http://127.0.0.1:%d" % a.port)
                           and not r["url"].startswith("devtools://")]
    finally:
        if proc:
            try: proc.terminate()
            except Exception: pass

    rep["shots"] = shots
    out = os.path.join(os.path.dirname(a.out), "_accept.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("报告：", os.path.relpath(out, ROOT))
    print("截图 %d 张 / 控制台错误 %d / 外部请求 %d"
          % (len(shots), len(rep["console"]), len(rep["external"])))
    for vp in rep["cases"]:
        ok = sum(1 for c in vp["cases"] if c.get("changed"))
        res = sum(1 for c in vp["cases"] if c.get("resetMatches"))
        print("  %s：改配件生效 %d/%d，恢复默认一致 %d/%d"
              % (vp["size"], ok, len(vp["cases"]), res, len(vp["cases"])))


if __name__ == "__main__":
    main()
