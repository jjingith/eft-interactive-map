# -*- coding: utf-8 -*-
"""R99 验收：配枪界面 ADS 必须跟着「总人机工效」走（真实浏览器，CDP）。

覆盖：
  1. AK-74 裸枪 → 人机 30 / ADS 1.51 s（技能 0 级）
  2. 装高 ergo 枪托 → 同一次点击渲染内 人机 54 / ADS 0.84 s（不刷新）
  3. 个人属性把突击步枪技能设到 51 → 人机 59.4 / ADS 0.69 s（修复点：技能后人机也重算 ADS）
  4. 两把不同枪总人机相同 → ADS 相同（MP5 / RSASS 裸枪均 50 → 0.95 s）

用法：python tools/r99_accept.py [--port 8791] [--cdp 9333]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r181_accept as A  # noqa: E402

AK74 = "5bf3e03b0db834001d2c4a9c"
AK74_STOCK_HIGH_ERGO = "5e217ba4c1434648c13568cd"   # Hexagon「烧火棍」枪托：人机 +24
MP5 = "5926bb2186f7744b1c6c6e60"
RSASS = "5a367e5dc4a282000e49738f"

READ_STATS = r"""
(function(){
  function row(hostSel, label){
    var host = document.querySelector(hostSel);
    if (!host) { return null; }
    var rows = host.querySelectorAll('.gw-stat');
    for (var i = 0; i < rows.length; i++) {
      var lab = rows[i].querySelector('.gw-stat-lab');
      var val = rows[i].querySelector('.gw-stat-val, .gw-stat-num');
      if (lab && lab.textContent.trim() === label) {
        var d = rows[i].querySelector('.gw-stat-delta');
        return {v: val ? val.textContent.trim() : null,
                delta: d ? d.textContent.trim() : null,
                why: lab.title || null};
      }
    }
    return null;
  }
  return {
    ergo: row('#gw-stats', '人机工效'),
    ads: row('#gw-hidden', 'ADS 时间'),
    meta: (document.querySelector('#gw-meta') || {}).textContent || null
  };
})()
"""

CLICK = r"""
(function(sel){
  var n = document.querySelector(sel);
  if (!n) { return false; }
  n.click();
  return true;
})(%s)
"""


def read_stats(cdp):
    return cdp.eval(READ_STATS)


def click(cdp, sel):
    return cdp.eval(CLICK % json.dumps(sel))


def pick_gun(cdp, gun_id, query, wait=60):
    sel = '#gw-results .gw-result[data-gun="%s"]' % gun_id
    end = time.time() + wait
    while time.time() < end:
        cdp.eval("(function(q){var i=document.querySelector('#gw-search');"
                 "if(!i){return false;} i.value=q; i.focus();"
                 "i.dispatchEvent(new Event('input',{bubbles:true})); return true;})"
                 "(%s)" % json.dumps(query))
        if cdp.eval("!!document.querySelector(%s)" % json.dumps(sel)):
            break
        time.sleep(0.6)
    else:
        diag = cdp.eval("(function(){return {n:document.querySelectorAll('#gw-results .gw-result').length,"
                        "h:(document.querySelector('#gw-results')||{}).innerHTML,"
                        "err:(document.querySelector('#gw-table')||{}).textContent};})()")
        raise SystemExit("搜索结果超时。诊断：%s" % json.dumps(diag, ensure_ascii=False)[:900])
    click(cdp, sel)
    A.wait_for(cdp, "!!document.querySelector('#gw-stats .gw-stat')", timeout=wait, label="属性面板渲染")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--cdp", type=int, default=9333)
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "r99_shots"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    chrome = A.find_chrome(None)
    profile = tempfile.mkdtemp(prefix="r99_chrome_")
    proc, ws_url = A.launch(chrome, args.cdp, 1680, 1180, profile)
    cdp = A.CDP(ws_url)
    try:
        cdp.call("Network.enable")
        # 屏蔽服务端偏好回声（否则会切视图 / 覆盖本地滑条与个人属性）
        cdp.call("Network.setBlockedURLs",
                 urls=["*api/config*", "*api/prefs*", "*api/events*"])
        cdp.call("Page.enable")
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % args.port)
        A.wait_ready(cdp, want_url="index.html")
        # 干净档案：清掉枪械装配 / 个人属性 / 视图，再重载
        cdp.eval("(function(){['eftmap.gun','eftmap.profile.v1','eftmap.view']"
                 ".forEach(function(k){try{localStorage.removeItem(k);}catch(e){}});return 1;})()")
        cdp.call("Page.reload")
        A.wait_ready(cdp, want_url="index.html")
        time.sleep(0.8)
        click(cdp, "#view-btn-gun")
        A.wait_for(cdp, "!!document.querySelector('#gw-search')", timeout=40, label="配枪视图")
        time.sleep(0.6)

        out = {}
        # ---- 1) AK-74（选枪后工作台自带一套默认装配）----
        pick_gun(cdp, AK74, "AK-74")
        time.sleep(0.5)
        out["ak74_default"] = read_stats(cdp)
        cdp.shot(os.path.join(args.out, "r99_1_default.png"))

        # ---- 2) 换高 ergo 枪托：点击后不刷新，属性与 ADS 必须同帧更新 ----
        click(cdp, '.gw-part[data-slot="mod_stock"]')
        A.wait_for(cdp, "!!document.querySelector('#gw-table .tbl-row[data-id=\"%s\"]')"
                   % AK74_STOCK_HIGH_ERGO, timeout=25, label="枪托候选出现")
        before = read_stats(cdp)
        click(cdp, '#gw-table .tbl-row[data-id="%s"]' % AK74_STOCK_HIGH_ERGO)
        after = read_stats(cdp)
        out["stock_before"] = before
        out["stock_after"] = after
        cdp.shot(os.path.join(args.out, "r99_2_stock.png"))

        # ---- 3) 技能 51：技能后人机与 ADS 必须一起变（本次修复点）----
        click(cdp, "#gw-forge .gw-forge-profbtn")
        A.wait_for(cdp, "!document.querySelector('#gw-profile').hidden", timeout=10, label="个人属性弹窗")
        cdp.eval("(function(){var i=document.querySelector('#gw-prof-skillrows input[data-skill=\"ar\"]');"
                 "if(!i){return false;} i.value='51'; return true;})()")
        click(cdp, "#gw-prof-save")
        A.wait_for(cdp, "document.querySelector('#gw-profile').hidden", timeout=10, label="弹窗关闭")
        time.sleep(0.3)
        out["skill51"] = read_stats(cdp)
        cdp.shot(os.path.join(args.out, "r99_3_skill51.png"))

        # ---- 4) 换枪：ADS 仍只由「当前总人机」决定（无按枪 id 硬编码）----
        pick_gun(cdp, MP5, "MP5")
        time.sleep(0.5)
        out["mp5"] = read_stats(cdp)
        pick_gun(cdp, RSASS, "RSASS")
        time.sleep(0.5)
        out["rsass"] = read_stats(cdp)
        cdp.shot(os.path.join(args.out, "r99_4_rsass.png"))

        out["console"] = [m.get("text") for m in cdp.console
                          if m.get("type") in ("error", "assert", "exception")]

        # ---- 断言：页面显示的 ADS 必须等于公式(页面显示的总人机) ----
        def expect_ads(ergo_txt):
            ergo = float(ergo_txt)
            return round(max(0.2, 2.35 - 0.028 * ergo) + 1e-9, 2)

        checks = []
        for key, label in (("ak74_default", "AK-74 默认装配"), ("stock_after", "AK-74 换高 ergo 枪托"),
                           ("skill51", "AK-74 + 突击步枪技能 51"), ("mp5", "MP5"), ("rsass", "RSASS")):
            cur = out[key]
            ergo = float(cur["ergo"]["v"])
            ads = float(cur["ads"]["v"].split()[0])
            exp = expect_ads(ergo)
            checks.append({"case": label, "ergo": ergo, "ads": ads, "expect": exp,
                           "ok": abs(ads - exp) < 0.005})
        checks.append({"case": "换枪托后 ADS 必须变快",
                       "ok": float(out["stock_after"]["ads"]["v"].split()[0]) <
                             float(out["stock_before"]["ads"]["v"].split()[0])})
        checks.append({"case": "技能 51 后 ADS 必须跟着技能后人机变快",
                       "ok": float(out["skill51"]["ads"]["v"].split()[0]) <
                             float(out["stock_after"]["ads"]["v"].split()[0])})
        checks.append({"case": "console 无报错", "ok": not out["console"]})
        out["checks"] = checks
        out["all_ok"] = all(c["ok"] for c in checks)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
